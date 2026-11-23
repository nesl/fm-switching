#!/usr/bin/env python3
"""D184 rung 3 ON THE c5attr BASE: the pass condition, the off-switch identity, and the name.

WHY THIS FILE EXISTS AND WHY IT IS NOT `d178_deficit_feed_proofs.py` RE-RUN. That file proved the
addendum 12 item 5 pass condition on the `covex-v6-state-shares` base. D184 then determined that
shares FAILS its three D179 (6) checks at three of four seeds, so the fallback fired and rung 2 is
`covex-v6-state-uo-c5attr`. The pass condition has to be re-proved ON THE BASE THAT WILL ACTUALLY
RUN, because the two bases differ in exactly the place that matters:

  CONSUMER 2, THE FLEXIBLE SPLIT, IS ABSENT BY CONSTRUCTION ON c5attr. The weights reach it only
  through `SA.allowed(weights_by_type=)`, and `share_admission._share_ok` returns before
  `SA.allowed` for an arm that does not enable share admission. `arms_v6c5.V6StateUoC5AttrArm` sets
  only `c5_attr_self_released`, so on this base the split consumer cannot deliver a weight at all.
  The building session recorded this as ABSENT BY CONSTRUCTION and it is EXPECTED to move zero
  decisions here. A zero from `splitonly` on this base is therefore NOT evidence about the policy;
  it is Rule 2's `unexpressible`, and it is pre-registered as such BEFORE the run.

  CONSUMER 1, THE ORDERING, DOES NOT GO THROUGH SHARE ADMISSION. It is the leading sort key at
  three sites in the frozen `hybrid/hybrid_arm.py`, overridden on the INNER HybridArm instance. It
  should fire on either base. THIS FILE CONFIRMS THAT RATHER THAN ASSUMING IT. The commit that
  posted the first c5attr rung-3 cell list said the consumer was "LIVE on that base, verified by
  construction rather than assumed" - construction is what Step 2b exists to not accept. If
  ordering also moves zero here, rung 3 CANNOT be run on the fallback base, and this file reports
  that as a STOP rather than working around it.

THE READ, named at the point of use rather than at the point of setting (CLAUDE.md Step 2):

  hybrid/hybrid_arm.py:399   `sorted(obs.recall, key=(self._deficit_order_key(...), x.deadline_s))`
  hybrid/hybrid_arm.py:483   `items.sort(key=(self._deficit_order_key(...), not risk, -idx, dl, id))`
  hybrid/hybrid_arm.py:486   the same sort on the C1-off branch

  All three CONSUME the value to change an order, and the order decides which items the C5 cap
  loop admits first, so the read changes a decision rather than only a log field. The frozen
  default returns 0.0, a constant, which cannot reorder anything; the rung-3 arm shadows it on the
  inner HybridArm with a plain function returning `-w_d`.

THE DEVICE THE HOOK SEES IS COUNTED, NOT ASSUMED. The previous attempt at this hook added a
`device_id` the frozen dataclasses did not have and received None on all 10,956 calls, so the
per-device weight collapsed to one value: a write-only field in the other direction. It was caught
by counting the hook's DISTINCT ARGUMENT VALUES, not by reading the code, so this file counts them
again on the base that will run (`order_hook` in every cell row).

THE INSTRUMENTATION IS PROVED INERT RATHER THAN ASSERTED. Every cell here, including the committed
baselines, is run with the same two wrappers: a counting shim around `_deficit_order_key` and a
per-period weight sampler around `decide`. If either moved a decision, `covex-v6-base`,
`v5-rules-2`, `covex-v6-state-uo` and `covex-v6-state-uo-c5attr` would not reproduce the digests
committed BEFORE any of this work. That is consistency check 7: the comparator's own numbers are
audited against committed values first, and two of these arms are positive controls that CANNOT
legitimately fail - if one of them does, the check is broken, not the arm.

NO SHIM. `d178_deficit_feed_proofs.py` needed `--order-shim` because the committed call sites could
not see a device. That fix landed at 3325e02c (stream_id IS the device for a dash stream; a recall
session resolves through the roster's `session_device` via `_device_of`). This file runs the
committed tree as it stands and has no shim of any kind.

ONE DRY CELL PER PROCESS, because dry decisions do not reproduce across runs INSIDE one process
(the open defect in spec v6 section 12). Every cell is a subprocess that decides nothing else.

DIGEST RECIPE, the established one, not re-derived:
    sha256(json.dumps(rows_without_arm_version, sort_keys=True, separators=(',',':'),
                      default=float)).hexdigest()[:16]
with the planner wall-clock cutoff patched off, so a digest is a property of the arm and not of how
busy this host was. A digest is comparable ONLY within this recipe.

Usage:
    python d184_r3_c5attr_proofs.py                 # the whole proof
    python d184_r3_c5attr_proofs.py --one ARM [--rows OUT.json]
    python d184_r3_c5attr_proofs.py --names-only    # item 3 alone
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ENTRY = HERE / "run_live2_real.py"
OUT = Path(os.environ.get(
    "D184_OUT",
    str(REPO / "results/orchestration/live2/frozen_test/d184_r3_c5attr_proofs.json")))

# The POSTED knobs (D187 cell list header), forwarded so a dry proof runs the cells' own workload.
CELL = dict(seed=4, n=16, run_s=1200.0, ratio="40:40:20", robot_question_set="lh_req",
            ss_question_set="ss2", dashcam_format="epg", robot_upload="per-frame",
            robot_reask_mean_s=30.0)
POSTED_CLI = ["--ratio", "40:40:20", "--robot-question-set", "lh_req", "--ss-question-set", "ss2",
              "--dashcam-format", "epg", "--robot-upload", "per-frame",
              "--robot-reask-mean-s", "30.0"]

BASE = "covex-v6-state-uo-c5attr"
RUNG3 = "covex-v6-fair-c5attr"

# Digests COMMITTED BEFORE this work. These are the bar. They are audited, never assumed.
COMMITTED: Dict[str, Dict[str, Any]] = {
    "covex-v6-base": dict(
        digest="af8befb9420ad86a", rows=12085,
        src="d179_offswitch_digest_proofs.json arms[covex-v6-base]; d187_r1_proofs.json "
            "off_switch_identity; c5attr_digest_proofs.json P1",
        role="POSITIVE CONTROL: a known-good committed arm that cannot legitimately fail"),
    "v5-rules-2": dict(
        digest="18067c4c66bb44b8", rows=11955,
        src="d179_offswitch_digest_proofs.json arms[v5-rules-2]; c5attr_digest_proofs.json P1",
        role="POSITIVE CONTROL: a known-good committed arm that cannot legitimately fail"),
    "covex-v6-state-uo": dict(
        digest="9a4be873eb3c5fba", rows=14218,
        src="d179_offswitch_digest_proofs.json arms[covex-v6-state-uo]; d187_r1_proofs.json and "
            "d187_r2_proofs.json off_switch_identity; c5attr_digest_proofs.json P1 and P3",
        role="the rung-1 parent of the c5attr base"),
    BASE: dict(
        digest="9a4be873eb3c5fba", rows=14218,
        src="c5attr_digest_proofs.json P3_dry_default_is_unexercised candidate",
        role="THE COMPARATOR for the off-switch identity, and the base rung 3 builds on. Equal to "
             "covex-v6-state-uo on a DRY cell because the C5 attribution rule needs measured "
             "first-token latency to fire and a dry cell has none (P3's own finding)."),
}


# ----------------------------------------------------------------------- one cell, one process
def _patch_planner_cutoff() -> None:
    import cf_instrument as CI
    for n in dir(CI):
        o = getattr(CI, n)
        if isinstance(o, type) and hasattr(o, "over_budget"):
            o.over_budget = lambda self, budget_ms=None: False


def _chain(obj: Any) -> List[Any]:
    out: List[Any] = []
    o: Any = obj
    seen = set()
    while o is not None and id(o) not in seen:
        seen.add(id(o))
        out.append(o)
        o = o.__dict__.get("_rules") or o.__dict__.get("_base")
    return out


def run_one(arm_name: str, rows_out: Optional[str], instr: bool = False) -> Dict[str, Any]:
    for p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
              str(HERE.parent / "baselines")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import arms as A  # noqa: F401
    import arms_v6fairfeed as FF
    import arms_v6state as VS
    VS.register()
    FF.register()
    _patch_planner_cutoff()
    import test_hybrid as TH

    samples: List[Dict[str, Any]] = []
    hook: Dict[str, Any] = {"calls": 0, "distinct_device_args": set(), "none_args": 0,
                            "distinct_key_values": set(), "nonzero_keys": 0, "kinds": set()}
    seen: Dict[str, Any] = {}

    def patch(arm: Any) -> None:
        """Record the object graph, and ONLY under `--instr` install any wrapper.

        MEASURED, NOT ASSUMED, AND IT COST A RE-RUN: the first pass of this proof wrapped
        `_deficit_order_key` and `decide` on every arm. `covex-v6-base`, `v5-rules-2` and
        `covex-v6-state-uo` still reproduced their committed digests under those wrappers, so the
        instrumentation looked inert - but `covex-v6-state-uo-c5attr` did NOT: it gave
        4dcd17bbcaf9262e / 14,203 against its committed 9a4be873eb3c5fba / 14,218, and the whole
        set reproduces the committed value once the wrappers are removed. A wrapper that is inert
        on three arms and not on the fourth is not inert. So the proof runs BARE, and the ordering
        evidence is taken from counters the PRODUCTION closure maintains itself
        (`order_key_resolved` / `order_key_unresolved_device` in `deficit_feed.counts`), which need
        no wrapper at all. `--instr` exists only to reproduce the artefact on demand."""
        seen["arm"] = arm
        chain = _chain(arm)
        core = next((o for o in reversed(chain)
                     if hasattr(type(o), "_deficit_order_key")), None)
        seen["core"] = type(core).__name__ if core is not None else None
        seen["instr"] = bool(instr)
        if core is not None:
            seen["overridden"] = vars(core).get("_deficit_order_key") is not None
        if not instr:
            return
        if core is not None:
            own = vars(core).get("_deficit_order_key")
            seen["overridden"] = own is not None
            if own is not None:
                def wrapped(device_id: Any, kind: Any, _f=own) -> float:
                    v = _f(device_id, kind)
                    _rec(device_id, kind, v)
                    return v
            else:
                _m = type(core)._deficit_order_key

                def wrapped(device_id: Any, kind: Any, _m=_m, _c=core) -> float:
                    v = _m(_c, device_id, kind)
                    _rec(device_id, kind, v)
                    return v
            object.__setattr__(core, "_deficit_order_key", wrapped)

        def _rec(device_id: Any, kind: Any, v: float) -> None:
            hook["calls"] += 1
            if device_id is None:
                hook["none_args"] += 1
            else:
                hook["distinct_device_args"].add(str(device_id))
            hook["kinds"].add(str(kind))
            if len(hook["distinct_key_values"]) < 4096:
                hook["distinct_key_values"].add(round(float(v), 6))
            if float(v) != 0.0:
                hook["nonzero_keys"] += 1

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

    t0 = time.time()
    la0 = os.getloadavg()
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
    arm = seen.get("arm")
    feed = arm.deficit_feed_report() if hasattr(arm, "deficit_feed_report") else None
    fc = dict((feed or {}).get("counts") or {})
    core_obj = _chain(arm)[-1] if arm is not None else None
    res = dict(
        arm=arm_name, seed=CELL["seed"], digest=digest, rows=len(rows),
        instrumented=bool(instr),
        # THE PRODUCTION COUNTERS. `order_key_resolved` and `order_key_unresolved_device` are
        # bumped inside the arm's OWN ordering closure (arms_v6fairfeed.py:174-179), so they are
        # evidence that needs no wrapper. A resolved count > 0 means the hook saw a device; the
        # per-device weight table below says how many distinct ones carried a weight.
        order_key_resolved=fc.get("order_key_resolved"),
        order_key_unresolved_device=fc.get("order_key_unresolved_device"),
        order_hook=dict(core=seen.get("core"), overridden=seen.get("overridden"),
                        instrumented=bool(instr),
                        calls=hook["calls"], none_args=hook["none_args"],
                        distinct_device_args=len(hook["distinct_device_args"]),
                        device_args_sample=sorted(hook["distinct_device_args"])[:8],
                        distinct_key_values=len(hook["distinct_key_values"]),
                        nonzero_keys=hook["nonzero_keys"],
                        kinds=sorted(hook["kinds"])),
        c5_attr=dict(flag_on_core=bool(getattr(core_obj, "c5_attr_self_released", False)),
                     attr_mon_len_at_end=len(getattr(core_obj, "_attr_mon", []) or []),
                     cap_at_end=getattr(core_obj, "cap", None),
                     counters={k: v for k, v in sorted(st.items())
                               if isinstance(v, (int, float)) and str(k).startswith("c5")}),
        share_counts={k: v for k, v in sorted(st.items()) if str(k).startswith("share_")
                      and not isinstance(v, dict)},
        deficit_feed_completions=st.get("deficit_feed_completions"),
        n_weight_samples=len(samples), feed=feed,
        host=dict(wall_s=round(time.time() - t0, 2), loadavg_start=list(la0),
                  loadavg_end=list(os.getloadavg()), pid=os.getpid()))
    if rows_out:
        Path(rows_out).write_text(json.dumps(
            dict(arm=arm_name, rows=rr, samples=samples, feed=feed), default=float) + "\n")
    return res


# ----------------------------------------------------------------------------------- the parent
def _cell(arm: str, keep: Optional[Path] = None, instr: bool = False) -> Dict[str, Any]:
    cmd = [sys.executable, str(Path(__file__).resolve()), "--one", arm]
    if keep is not None:
        cmd += ["--rows", str(keep)]
    if instr:
        cmd.append("--instr")
    env = dict(os.environ, PYTHONHASHSEED="0")
    p = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True, timeout=10800, env=env)
    line = [l for l in p.stdout.splitlines() if l.startswith("{")]
    if p.returncode or not line:
        return dict(arm=arm, error=(p.stderr or p.stdout)[-2000:])
    return json.loads(line[-1])


def _weight_stats(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
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


def _weights_from_feed(cell: Dict[str, Any]) -> Dict[str, Any]:
    """Per-device weights AT END OF RUN, read from the arm's own `deficit_feed_report`.

    This is the register the bare run can report: one value per device at the end, not a
    distribution over time, because sampling over time needs a wrapper and a wrapper is what
    perturbed a cell. Stated as such rather than presented as the same quantity.
    """
    pd = ((cell.get("feed") or {}).get("per_device") or {})
    per = {d: float(v.get("weight") or 0.0) for d, v in pd.items()}
    if not per:
        return {"_ALL": None}
    vals = sorted(per.values())
    out: Dict[str, Any] = {d: dict(weight=round(w, 6),
                                   shortfall=round(float(pd[d].get("shortfall") or 0.0), 6),
                                   type=pd[d].get("type"))
                           for d, w in sorted(per.items())}
    out["_ALL"] = dict(min=round(vals[0], 6), max=round(vals[-1], 6),
                       median=round(statistics.median(vals), 6),
                       constant_at_one=bool(vals[0] == 1.0 == vals[-1]),
                       devices=len(vals),
                       devices_above_one=sum(1 for w in vals if w > 1.0),
                       distinct=len(set(round(w, 6) for w in vals)),
                       register="end-of-run value per device, NOT a distribution over time")
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


# ------------------------------------------------------------------- item 3: the name resolves
NAME_ARMS = [RUNG3, RUNG3 + "-off", RUNG3 + "-gain0", RUNG3 + "-orderonly",
             RUNG3 + "-splitonly"]
UNKNOWN = RUNG3 + "-not-an-arm"
MARKER = "unknown arm"


def _name_probe(name: str, seed: int = 0) -> Dict[str, Any]:
    """The HARNESS'S OWN entry point on this name. `run_live2_real.py` imports only `arms` and
    `hybrid`, so a name that resolves in a friendly process can still die at cell start: the v6
    names did exactly that once, at arms.py KeyError 80 s in, and four cells were skipped."""
    with tempfile.TemporaryDirectory(prefix="d184r3_") as td:
        p = subprocess.run(
            [sys.executable, str(ENTRY), "--arm", name, "--out", str(Path(td) / "cell"),
             "--n-devices", "2", "--run-s", "5", "--seed", str(seed)] + POSTED_CLI,
            cwd=str(HERE), capture_output=True, text=True, timeout=1800)
    blob = (p.stdout or "") + (p.stderr or "")
    return {"arm": name, "seed": seed, "returncode": p.returncode,
            "raised_unknown_arm": MARKER in blob,
            "tail": blob.strip().splitlines()[-1][:300] if blob.strip() else ""}


def name_proofs() -> Dict[str, Any]:
    neg = _name_probe(UNKNOWN)
    out: Dict[str, Any] = {
        "_claim": ("every rung-3 c5attr name reaches make_arm in the HARNESS'S own process, and "
                   "an unknown name on the same path still raises"),
        "entry_point": str(ENTRY.relative_to(REPO)),
        "posted_knobs": POSTED_CLI,
        "negative_control": dict(
            probe=neg,
            _why=("'no KeyError appeared' passes trivially if the subprocess never reached "
                  "make_arm, if the parser rejected something first, or if the grep looks for the "
                  "wrong string"),
            verdict=("PASS: the check can see an unresolved name" if neg["raised_unknown_arm"]
                     else "FAIL: THE CHECK IS BROKEN, not the arm: an unknown name did not "
                          "produce %r" % MARKER)),
    }
    if not neg["raised_unknown_arm"]:
        out["probes"] = []
        out["verdict"] = "FAIL: negative control did not raise, so resolution means nothing"
        return out
    rows = [_name_probe(n) for n in NAME_ARMS]
    out["probes"] = rows
    bad = [r["arm"] for r in rows if r["raised_unknown_arm"]]
    out["verdict"] = ("PASS: all %d names resolve" % len(rows) if not bad
                      else "FAIL: did not resolve: %s" % bad)
    return out


# -------------------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--one")
    ap.add_argument("--rows")
    ap.add_argument("--names-only", action="store_true")
    ap.add_argument("--instr", action="store_true",
                    help="install the counting wrappers; NOT used by the proof, kept only to "
                         "reproduce the perturbation they caused on covex-v6-state-uo-c5attr")
    a = ap.parse_args()
    if a.one:
        print(json.dumps(run_one(a.one, a.rows, instr=a.instr), default=float))
        return 0

    tmp = Path(os.environ.get("D184_SCRATCH", "/tmp")) / "d184_r3"
    tmp.mkdir(parents=True, exist_ok=True)

    out: Dict[str, Any] = {
        "_what": ("D184 rung 3 on the c5attr base: the addendum 12 item 5 pass condition with "
                  "per-consumer attribution, the off-switch identity against values committed "
                  "BEFORE the change, and the name proof through run_live2_real.py itself"),
        "_why_rerun_on_this_base": (
            "d178_deficit_feed_proofs.json proved the pass condition on covex-v6-state-shares. "
            "D184 determined shares fails its three D179 (6) checks at three of four seeds, so "
            "rung 2 is covex-v6-state-uo-c5attr and the pass condition must hold ON THE BASE THAT "
            "WILL RUN. The two bases differ in exactly the place that matters: share admission."),
        "_protocol": ("ONE dry cell per process (subprocess), planner wall-clock cutoff patched "
                      "off, POSTED knobs forwarded, seed 4, NO SHIM of any kind"),
        "_digest_recipe": ("sha256(json.dumps(rows without arm_version, sort_keys=True, "
                           "separators=(',',':'), default=float))[:16]; comparable only within "
                           "this recipe"),
        "_form": ("w_d = 1 + 2.0 * (shortfall_d / target_d), floored at 1, PER DEVICE; range "
                  "[1, 3]; GAIN pre-registered in deficit_gain_d178.py"),
        "_the_read": {
            "ordering_PRIMARY": [
                "hybrid/hybrid_arm.py:399 sorted(obs.recall, key=(_deficit_order_key(...), dl))",
                "hybrid/hybrid_arm.py:483 items.sort(key=(_deficit_order_key(...), ...))",
                "hybrid/hybrid_arm.py:486 the same sort on the C1-off branch",
                "all three USE the value to change an order, and the order decides which items "
                "the C5 cap loop admits first"],
            "flexible_split": [
                "share_admission.py:162-168 via the coordinator's SA.allowed(weights_by_type=)",
                "PRE-REGISTERED AS ABSENT ON THIS BASE: _share_ok returns before SA.allowed for "
                "an arm that does not enable share admission, and V6StateUoC5AttrArm sets only "
                "c5_attr_self_released, so the weights have NO READER on the c5attr base"],
        },
        "_prereg_pass_condition": (
            "PASS: gain 2.0 against gain 0 shows differing decision rows SETWISE and the count is "
            "ATTRIBUTABLE to a named consumer. FAILURE: zero differing decisions, in which case "
            "rung 3 on this base is a NON-CONTRIBUTION, is NOT TUNED, and no cell list is posted "
            "(a rung-3 cell whose ordering consumer does not fire would be a rename)."),
        "_prereg_expected_split_zero": (
            "The SPLIT consumer is expected to move ZERO on this base, by construction, and that "
            "zero is Rule 2's `unexpressible`, not evidence about the policy. The pass therefore "
            "rests on the ORDERING consumer alone, which is also the consumer addendum 12 item 3a "
            "calls the PRIMARY one."),
        "cell": dict(CELL),
        "committed_bar": COMMITTED,
    }

    if a.names_only:
        out["item3_name_proof"] = name_proofs()
        print(json.dumps(out["item3_name_proof"], indent=1)[:4000])
        return 0

    # CONCURRENCY IS A MEASUREMENT PARAMETER HERE, NOT AN IMPLEMENTATION DETAIL, and it was
    # measured the hard way. At max_workers=9 (loadavg about 9 on 24 cores) the cell
    # covex-v6-state-uo-c5attr gave 4dcd17bbcaf9262e / 14,203 against its committed
    # 9a4be873eb3c5fba / 14,218, and wall time per cell was about 600 s. The SAME arm with the
    # SAME wrappers at loadavg 2 gave the committed digest in 218 s, and so did the bare run. So
    # the dry path retains a wall-clock sensitivity that the `cf_instrument.over_budget` patch
    # does not cover - this is the reproduce-across-runs defect named at 3325e02c - and the
    # remedy is to keep the host quiet, declare the concurrency, and carry a self-reproduction
    # control on the comparator rather than to assume a digest is a pure function of the arm.
    MAX_WORKERS = int(os.environ.get("D184_WORKERS", "4"))
    from concurrent.futures import ThreadPoolExecutor
    pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    # ---- item 3 first: it is cheap, and a name that does not resolve makes the cells pointless
    out["item3_name_proof"] = name_proofs()
    print("name proof:", out["item3_name_proof"]["verdict"], flush=True)

    # ---- every cell, concurrently. Rows kept where a row-level diff needs them.
    keep: Dict[str, Path] = {}
    futs: Dict[str, Any] = {}
    identity_arms = ["covex-v6-base", "v5-rules-2", "covex-v6-state-uo", BASE, RUNG3 + "-off"]
    treat_arms = [RUNG3 + "-gain0", RUNG3, RUNG3 + "-orderonly", RUNG3 + "-splitonly"]
    REPEAT = RUNG3 + "-gain0#repeat"
    for arm in identity_arms + treat_arms + [REPEAT]:
        real = arm.split("#")[0]
        f = None
        if real in treat_arms or real == BASE:
            f = tmp / ("rows_%s.json" % arm.replace("-", "_").replace("#", "_"))
            keep[arm] = f
        futs[arm] = pool.submit(_cell, real, f)
    cells = {}
    for arm, fut in futs.items():
        cells[arm] = fut.result()
        print("%-36s %s rows=%s order_key_resolved=%s unresolved=%s load=%.2f" % (
            arm, cells[arm].get("digest"), cells[arm].get("rows"),
            cells[arm].get("order_key_resolved"),
            cells[arm].get("order_key_unresolved_device"),
            ((cells[arm].get("host") or {}).get("loadavg_end") or [0])[0]), flush=True)

    out["_determinism_control"] = dict(
        _claim=("the COMPARATOR is run twice, in two separate processes at this concurrency, and "
                "must give the same digest. Without this, a difference between gain 2.0 and gain "
                "0 could be the wall-clock sensitivity rather than the mechanism."),
        comparator=RUNG3 + "-gain0",
        run1=dict(digest=cells[RUNG3 + "-gain0"].get("digest"),
                  rows=cells[RUNG3 + "-gain0"].get("rows"),
                  wall_s=(cells[RUNG3 + "-gain0"].get("host") or {}).get("wall_s")),
        run2=dict(digest=cells[REPEAT].get("digest"), rows=cells[REPEAT].get("rows"),
                  wall_s=(cells[REPEAT].get("host") or {}).get("wall_s")),
        max_workers=MAX_WORKERS,
        self_reproduces=bool(cells[REPEAT].get("digest")
                             == cells[RUNG3 + "-gain0"].get("digest")
                             and cells[REPEAT].get("rows")
                             == cells[RUNG3 + "-gain0"].get("rows")),
        verdict=("PASS" if (cells[REPEAT].get("digest")
                            == cells[RUNG3 + "-gain0"].get("digest")) else
                 "FAIL: the comparator does not reproduce at this concurrency, so NO digest "
                 "comparison in this file may be read"))

    def thin(r: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in r.items() if k != "feed"}

    # ---- item 2: the off-switch identity, each arm against a value committed BEFORE the change
    id_rows = []
    for arm in identity_arms:
        r = thin(dict(cells[arm]))
        bar = COMMITTED.get(arm)
        r["committed"] = bar
        r["agrees"] = (None if bar is None else
                       bool(r.get("digest") == bar["digest"] and r.get("rows") == bar["rows"]))
        id_rows.append(r)
    base_d = cells[BASE].get("digest")
    off_d = cells[RUNG3 + "-off"].get("digest")
    bar_ok = all(r["agrees"] is not False for r in id_rows)
    out["item2_off_switch_identity"] = dict(
        _claim=("with live2_deficit_feed OFF, covex-v6-fair-c5attr is byte-identical to "
                "covex-v6-state-uo-c5attr, and every non-rung-3 arm is unchanged against a value "
                "committed BEFORE the change"),
        _control_validated=(
            "consistency check 7: %s is the COMPARATOR for every treatment below, so its own "
            "digest is checked against a committed value FIRST. A broken control passes every "
            "check applied to the treatment." % BASE),
        _positive_controls=("covex-v6-base and v5-rules-2 are known-good committed arms and MUST "
                            "pass. If one of them fails, the CHECK is broken, not the arm."),
        _no_instrumentation=(
            "every cell here runs BARE: no wrapper on `_deficit_order_key`, none on `decide`, no "
            "shim on any dataclass. An earlier pass wrapped both, and although the wrappers turn "
            "out NOT to be the cause, the bare run is the honest register: see "
            "`_wallclock_sensitivity`."),
        rows=id_rows,
        off_digest=off_d, base_digest=base_d,
        off_equals_base=bool(off_d == base_d),
        off_equals_committed_base=bool(off_d == COMMITTED[BASE]["digest"]
                                       and cells[RUNG3 + "-off"].get("rows")
                                       == COMMITTED[BASE]["rows"]),
        committed_bar_all_agree=bar_ok,
        verdict=("PASS" if (bar_ok and off_d == base_d
                            and off_d == COMMITTED[BASE]["digest"]) else "FAIL"))

    # ---- item 1: the pass condition, four ways against ONE comparator
    def _rows(p: Path) -> List[Dict[str, Any]]:
        return json.loads(p.read_text())["rows"]

    def _samples(p: Path) -> List[Dict[str, Any]]:
        return json.loads(p.read_text())["samples"]

    g0 = _rows(keep[RUNG3 + "-gain0"])
    attrib: Dict[str, Any] = {}
    for tag, arm in (("both", RUNG3), ("orderonly", RUNG3 + "-orderonly"),
                     ("splitonly", RUNG3 + "-splitonly")):
        c = cells[arm]
        attrib[tag] = dict(
            arm=arm, digest=c.get("digest"), rows=c.get("rows"),
            identical_to_gain0=bool(c.get("digest") == cells[RUNG3 + "-gain0"].get("digest")),
            order_key_resolved=c.get("order_key_resolved"),
            order_key_unresolved_device=c.get("order_key_unresolved_device"),
            diff_vs_gain0=_diff(g0, _rows(keep[arm])))
    moved_order = attrib["orderonly"]["diff_vs_gain0"]["setwise"]
    moved_split = attrib["splitonly"]["diff_vs_gain0"]["setwise"]
    moved_both = attrib["both"]["diff_vs_gain0"]["setwise"]
    out["item1_pass_condition"] = dict(
        _claim=out["_prereg_pass_condition"],
        comparator=dict(
            arm=RUNG3 + "-gain0", digest=cells[RUNG3 + "-gain0"].get("digest"),
            rows=cells[RUNG3 + "-gain0"].get("rows"),
            _why=("gain 0 and not the rung-2 base: it leaves BOTH consumers, every hook and every "
                  "counter live and removes ONLY the quantity under test, so a difference cannot "
                  "be attributed to the plumbing"),
            equals_rung2_base=bool(cells[RUNG3 + "-gain0"].get("digest") == base_d),
            equals_committed_base=bool(cells[RUNG3 + "-gain0"].get("digest")
                                       == COMMITTED[BASE]["digest"])),
        by_consumer=attrib,
        attribution=dict(
            ordering_alone_setwise=moved_order, split_alone_setwise=moved_split,
            both_setwise=moved_both,
            ordering_alone_positional=attrib["orderonly"]["diff_vs_gain0"]["positional"],
            split_alone_positional=attrib["splitonly"]["diff_vs_gain0"]["positional"],
            both_positional=attrib["both"]["diff_vs_gain0"]["positional"],
            both_equals_orderonly=bool(attrib["both"]["digest"]
                                       == attrib["orderonly"]["digest"]),
            _note=("ordering and split are not required to add up: they interact through which "
                   "request is admitted first. The three numbers are reported separately, never "
                   "summed. On this base the split is ABSENT BY CONSTRUCTION and a zero from it "
                   "is Rule 2's `unexpressible`.")),
        verdict=("PASS" if moved_both > 0 and moved_order > 0 else
                 "STOP: THE ORDERING CONSUMER DOES NOT MOVE A DECISION ON THE c5attr BASE. "
                 "Rung 3 CANNOT be run on the D184 fallback base. No cell list is posted."))

    # ---- the weights vary, and the gain-0 control
    w3 = _weights_from_feed(cells[RUNG3])
    g0w = _weights_from_feed(cells[RUNG3 + "-gain0"])
    out["item1b_weights_vary"] = dict(
        _claim=("the per-device weights vary ACROSS DEVICES; a weight constant at 1.0 everywhere "
                "means the feed is CONSTANT, a stopping condition and not a result"),
        _register=("END-OF-RUN value per device, from the arm's own deficit_feed_report. NOT a "
                   "distribution over time: sampling over time needs a wrapper, and a wrapper is "
                   "what perturbed a cell here. The over-time spread on the SHARES base is in "
                   "d178_deficit_feed_proofs.json and is not re-claimed for this base."),
        both=w3, gain0=g0w, feed_at_end=cells[RUNG3].get("feed"))
    out["item1c_negative_control_gain0"] = dict(
        _claim=("CLAUDE.md Step 4: gain 0 leaves every hook, counter and BOTH consumers live and "
                "removes only the quantity under test, so every weight must be exactly 1.0 and "
                "the arm must collapse to the rung-2 base"),
        all_weights_one=bool((g0w.get("_ALL") or {}).get("constant_at_one")),
        devices_seen=(g0w.get("_ALL") or {}).get("devices"),
        order_key_resolved=cells[RUNG3 + "-gain0"].get("order_key_resolved"),
        digest=cells[RUNG3 + "-gain0"].get("digest"), base_digest=base_d,
        identical_to_base=bool(cells[RUNG3 + "-gain0"].get("digest") == base_d),
        verdict=("PASS" if (g0w.get("_ALL") or {}).get("constant_at_one")
                 and cells[RUNG3 + "-gain0"].get("digest") == base_d else "FAIL"))

    res3 = int(cells[RUNG3].get("order_key_resolved") or 0)
    unres3 = int(cells[RUNG3].get("order_key_unresolved_device") or 0)
    out["item2b_step2b_device_visible"] = dict(
        _claim=("the ordering hook RESOLVES A DEVICE on this base, counted by the arm's own "
                "closure rather than by a wrapper. The previous inert fix was caught by counting "
                "the hook's arguments: it received None on all 10,956 calls and the per-device "
                "weight collapsed to one value."),
        _read=("arms_v6fairfeed.py:174-179 bumps order_key_unresolved_device or "
               "order_key_resolved inside the function that hybrid_arm.py:399/483/486 call"),
        rung3=dict(order_key_resolved=res3, order_key_unresolved_device=unres3,
                   devices_with_a_weight=(w3.get("_ALL") or {}).get("devices"),
                   distinct_weights=(w3.get("_ALL") or {}).get("distinct")),
        gain0=dict(order_key_resolved=cells[RUNG3 + "-gain0"].get("order_key_resolved"),
                   order_key_unresolved_device=cells[RUNG3 + "-gain0"]
                   .get("order_key_unresolved_device")),
        base=dict(order_key_resolved=cells[BASE].get("order_key_resolved"),
                  _note="the base has no feed, so it has no counter: None is expected here"),
        verdict=("PASS" if (res3 > 0 and (w3.get("_ALL") or {}).get("devices_above_one", 0) > 0
                            and not (w3.get("_ALL") or {}).get("constant_at_one"))
                 else "FAIL"))

    out["_wallclock_sensitivity"] = dict(
        _what=("consistency checks 1 and 7, and a finding in its own right. A first pass of this "
               "proof ran 9 cells at once and ONE of them disagreed with its committed value. "
               "The discrepancy is recorded here with its cause rather than dropped, and the "
               "cause is NOT the one it first looked like."),
        _caching_register=("every cell here is a DRY cell: no engine, no server, no prefix cache, "
                           "and no measurement of a model's latency. The sensitivity below is to "
                           "HOST WALL CLOCK inside the decision path, not to any cache."),
        disagreeing_cell=dict(
            arm=BASE, digest="4dcd17bbcaf9262e", rows=14203,
            committed="9a4be873eb3c5fba / 14218",
            concurrency=9, loadavg_about=9, wall_s_about=600,
            _note=("the other 8 cells of that pass DID reproduce their expected digests, "
                   "including the two positive controls, so arm-versus-arm checking could not "
                   "have seen this")),
        probe_that_separated_the_two_hypotheses=dict(
            _design=("the same arm, the same wrappers, run ALONE at loadavg 2. If the wrappers "
                     "were the cause the digest would still disagree; if host load was the cause "
                     "it would agree."),
            instrumented_at_load_2=dict(digest="9a4be873eb3c5fba", rows=14218, wall_s=218.42,
                                        loadavg_start=1.03),
            bare_at_load_2=dict(digest="9a4be873eb3c5fba", rows=14218),
            conclusion=("HOST LOAD, not the instrumentation. The wrappers are exonerated and the "
                        "dry path retains a wall-clock sensitivity that the "
                        "`cf_instrument.over_budget` patch does not cover. This is the "
                        "reproduce-across-runs defect named at 3325e02c, now with a measured "
                        "trigger: concurrency.")),
        bare_rerun_at_this_concurrency=dict(
            arm=BASE, digest=cells[BASE].get("digest"), rows=cells[BASE].get("rows"),
            agrees_with_committed=bool(cells[BASE].get("digest")
                                       == COMMITTED[BASE]["digest"])),
        c5_attr_counters_bare=cells[BASE].get("c5_attr"),
        why_this_arm=("the C5 attribution rule is the one mechanism in this set gated on a "
                      "latency EWMA. Bare and quiet, it is UNEXERCISED in dry: `_attr_mon` is "
                      "empty at end of run, `cap` is still 8 and no c5_attr counter exists at "
                      "all, which is exactly what c5attr_digest_proofs.json P3 recorded as "
                      "`P3_dry_default_is_unexercised`. Under load the cap moved, so the one arm "
                      "with a timing-gated rule was the one arm perturbed."),
        consequence_for_this_file=("every number reported here comes from a BARE run at declared "
                                   "concurrency %d, with the comparator run twice as a "
                                   "self-reproduction control (see _determinism_control)."
                                   % MAX_WORKERS),
        consequence_for_others=("a dry digest from this harness is a property of the arm AND of "
                                "how busy the host was. Proof scripts here that run many cells "
                                "at once should carry a self-reproduction control; "
                                "d179_offswitch_digest_proofs.json ran at concurrency 18 and "
                                "carries one for covex-v6-state-uo only."))

    verdicts = {k: out[k].get("verdict") for k in
                ("_determinism_control", "item1_pass_condition",
                 "item1c_negative_control_gain0",
                 "item2_off_switch_identity", "item2b_step2b_device_visible")}
    verdicts["item3_name_proof"] = out["item3_name_proof"]["verdict"]
    out["verdicts"] = verdicts
    out["verdict"] = ("ALL_PASS" if all(str(v).startswith("PASS") for v in verdicts.values())
                      else "FAIL/STOP: " + "; ".join("%s=%s" % (k, str(v)[:60])
                                                     for k, v in verdicts.items()
                                                     if not str(v).startswith("PASS")))

    try:
        sys.path.insert(0, str(REPO / "experiments/lib"))
        from _provenance import stamp  # type: ignore
        out["_provenance"] = stamp(script="d184_r3_c5attr_proofs.py", model="n/a",
                                   device="cpu_dry", n=CELL["n"], args=None)
    except Exception:                                                        # noqa: BLE001
        out["_provenance"] = {}
    out["_provenance"].update(
        git_commit=os.environ.get("D184_CODE_REF", "unknown"),
        _git_commit_register=("the commit the MEASUREMENT RAN ON: the code tree is `git archive "
                              "<this ref> experiments`, not origin/main at writing time"),
        script="experiments/orchestration/live2/d184_r3_c5attr_proofs.py",
        host="flash", n_cells=len(futs), max_workers=MAX_WORKERS)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(verdicts, indent=1))
    print(out["verdict"])
    print("wrote", OUT)
    return 0 if out["verdict"] == "ALL_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
