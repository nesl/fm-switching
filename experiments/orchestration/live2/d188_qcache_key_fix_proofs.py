#!/usr/bin/env python3
"""D188 (2): the `_queued_behind` cache-key fix, prepared BEHIND AN OFF-BY-DEFAULT SWITCH.

THE USER'S RULING. The defect at `arms_v6state.py` is an implementation bug to be FIXED TOMORROW.
It is NOT applied to any cell tonight. What this file produces is the two things tomorrow needs:

  (a) BYTE-IDENTITY WITH THE SWITCH OFF, on every arm that is not a rung-2 arm, each audited
      against a digest COMMITTED BEFORE the change
      (`results/orchestration/live2/frozen_test/d179_offswitch_digest_proofs.json`), not merely
      against itself. A control that is only compared with itself cannot fail.
  (b) A DRY MEASUREMENT of how many rung-2 decisions the fix changes, switch ON against switch
      OFF, reported SETWISE and POSITIONALLY with the first differing row, so the rung-2 rerun can
      be scoped before it is run.

THE DEFECT, confirmed in code and not rediscovered here:

    key = (int(obs.epoch) if isinstance(obs.epoch, int) else id(obs))   arms_v6state.py (before)
    def observation(self, now: float, epoch: str, ...)                  cstate.py:579

`obs.epoch` is always a str, the isinstance test is always False, and the single-slot cache is
therefore keyed on a MEMORY ADDRESS that CPython reuses.

WHAT IS MEASURED AND WHAT IS NOT. A DRY REPLAY MEASURES DRY ALLOCATION PATTERNS. A live run has a
real backend, I/O threads and a different allocation history, so every stale-hit count and every
decision delta below is an INDICATION of live exposure and NOT a measurement of it. This file does
not bound the live effect and does not let the dry number stand in for it.

ONE DRY CELL PER PROCESS. A second dry cell inside one process does not reproduce the first, and
that non-reproduction is the very defect under study, so this is not optional: every digest here
is produced by its own `--one-cell` subprocess.

THE COUNTING WRAPPER IS RUN IN ITS OWN CELL AND NEVER IN A DIGEST CELL. The wrapper allocates, so
it perturbs exactly the address reuse it is counting; a digest taken under it is not comparable
with a committed digest taken without it. Digest cells are unwrapped; stale-hit counts come from a
separate wrapped cell and are labelled as such.

THE PLANNER WALL-CLOCK CUTOFF IS PATCHED OFF in every cell here, as in the committed D179 proof
these digests are audited against, because these cells run concurrently and a load-dependent
abandon would make the digest a property of the load. Live cells keep it ON (D99 (3)).

Usage:
  switch scope only:  d188_qcache_key_fix_proofs.py --switch-tests --root <tree>
  one cell:           d188_qcache_key_fix_proofs.py --one-cell --root <tree> --arm <arm>
                          --seed 4 --fix off|on [--count] --out <path>
  driver:             d188_qcache_key_fix_proofs.py --before-root <tree> --after-root <tree>
                          --base-sha <sha> --work <scratch dir> [--seeds 4] [--jobs 12]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

# the posted workload knobs. `test_hybrid.dry` defaults to oneframe dashcam bodies, batch-30s
# upload and no re-asks, which is a DIFFERENT workload and would measure the wrong thing.
POSTED = dict(ratio="40:40:20", robot_question_set="lh_req", ss_question_set="ss2",
              dashcam_format="epg", robot_upload="per-frame", robot_reask_mean_s=30.0)
CELL = dict(n=16, run_s=1200.0)
ALLOWED_SEEDS = (0, 4, 5, 6, 7)

SWITCH = "live2_qcache_key_fix"

# the arms the OFF-path byte-identity gate is stated over. covex-v6-state-uo is IN this list on
# purpose: it is the rung-2 arm, and with the switch OFF it must still reproduce its committed
# digest. That is the positive control on this harness - a known-good committed arm reproducing a
# committed value. If it fails, the harness is broken, not the arm.
IDENTITY_ARMS = (
    "covex-v6-base", "v5-rules-2", "b7-edf-feasibility", "always-cloud-fcfs", "edf", "llf",
    "mooncake", "attentionstore-prefetch", "simplestream", "querystream-proactive",
    "warm-all-lru", "confidence-cascade", "eco-llm", "covex-v6-state-uo",
)
# the arms the dry ON-against-OFF decision delta is measured on
RUNG2_ARMS = ("covex-v6-state-uo", "covex-v6-state-uo-c5attr", "covex-v6-state-shares",
              "covex-v6-state-shares-r1", "covex-v6-state-shares-r2")

# THE CRUX. One session saw ZERO differing decisions WITHIN an arm (the key as the only
# difference, allocation history held fixed) and another saw 575 differing decisions collapse to 0
# under the fix when comparing a switch-OFF WRAPPER arm against its BASE, which is a comparison
# between two arms with DIFFERENT allocation histories. The offered reconciliation is that the
# defect damages CROSS-ARM byte-identity proofs and not an arm's own decisions. That claim decides
# whether tomorrow's rerun needs the comparators rerun too, so it is TESTED here and not accepted:
# `covex-v6-state-shares-off` is the DECLARED Step-4 negative control that must collapse to
# `covex-v6-state-uo` (arms_v6shares.py), which is exactly the wrapper-against-base shape. If the
# pair disagrees with the switch OFF and agrees with it ON, the reconciliation is confirmed.
CROSS_ARM_PAIRS = (("covex-v6-state-shares-off", "covex-v6-state-uo"),)
CROSS_ARMS = tuple(dict.fromkeys([x for pair in CROSS_ARM_PAIRS for x in pair]))

# CLAUDE.md Step 4: an arm that never enters V6StateArm cannot see the key at all, so turning the
# switch ON for it must collapse to its own OFF digest AND to its committed value. If it does not,
# whatever moves the rung-2 cells is not this key.
NEGCTRL_ARM = "covex-v6-base"

COMMITTED = REPO / "results/orchestration/live2/frozen_test/d179_offswitch_digest_proofs.json"


# CLAUDE.md mechanism verification, written BEFORE the sweep ran and recorded with it.
MECHANISM = {
 "step0_what_would_invalidate_this_run": [
  ("The committed digests this is audited against were produced at sha f3482026 and origin/main "
   "has moved since, so a disagreeing digest could be this change OR an intervening commit. Every "
   "disagreeing arm is therefore re-run on the UNPATCHED tree to attribute it "
   "(proof_a_moved_arms_attributed). None disagreed."),
  ("A dry cell does not reproduce across runs inside one process, and that non-reproduction IS "
   "the defect under study, so every cell here is its own process."),
  ("Under concurrency the planner wall-clock cutoff makes a digest a property of the machine "
   "load; it is patched off here, as it was in the committed proof being compared against. Live "
   "cells keep it ON (D99 (3))."),
  ("The counting wrapper allocates and so perturbs the address reuse it counts; it is never "
   "installed in a cell whose digest is compared with anything."),
  ("The OFF path runs inside the planner's wall-clock budget, so an MRO scan per call would "
   "charge that budget for a switch that is off; the switch is resolved once per arm instance."),
 ],
 "step1_causal_chain": (
  "The `_queued_behind` single-slot cache is keyed on id(obs), because `obs.epoch` is a str and "
  "the isinstance(int) test never fires (cstate.py:579). CPython reuses addresses, so an "
  "Observation allocated where a freed one sat HITS an entry written in a previous decision "
  "period. That entry's rows carry a slack_s computed as deadline_s - now_s with the OTHER "
  "period's now_s. `_harm_warm` reads the filtered list and prices it through "
  "`cf_objective.harm_warm_from_queue_delay`, so the `hw` and `harm_touch` reaching "
  "`cf.plan_state` differ from their correct values; plan_state scores HOLD_BACK at harm_warm and "
  "SLICE at half of it against WARM, TOUCH and KEEP, so `d.chosen` can change, and a changed "
  "choice emits a different KEEP_GPU_WARM SessionAction or removes a MATERIALIZE ask, which is a "
  "different decision row. The D162 one-price source is the user ruling of 2026-11-21 that this "
  "term and the request-decision harm stay in one currency (D171 (2))."),
 "step2_instantiation": [
  {"causal link": "the key is an address, not a decision period",
   "implementing quantity": "qcache_counts.stale_hits",
   "where to read it": "proof_b stale_hits_from_a_separate_WRAPPED_off_cell",
   "varies as expected": "non-zero on the rung-2 arms, and zero on any arm that never enters "
                         "V6StateArm",
   "evidence": "the counting wrapper; and the isolated key trace in step3_isolated_key_trace, "
               "where the OFF key is an integer address that does not change between two "
               "different now_s and the ON key is (epoch, now_s)"},
  {"causal link": "a stale entry reaches `_harm_warm`",
   "implementing quantity": "qcache_counts.stale_hits_returned_nonempty",
   "where to read it": "proof_b; a stale hit returning an EMPTY list cannot change a harm sum and "
                       "is counted apart",
   "varies as expected": "must be non-zero for the chain to be live",
   "evidence": "`_queued_behind` returns the filtered list and `_harm_warm` consumes it"},
  {"causal link": "the priced harm differs",
   "implementing quantity": "arm_stats.harm_warm_nonzero / harm_warm_milli_sum",
   "where to read it": "proof_b, ON against OFF per cell",
   "varies as expected": "must move between ON and OFF if the stale value is priced",
   "evidence": "the stats written in `_harm_warm`"},
  {"causal link": "the choice moves",
   "implementing quantity": "the decision-row digest and the setwise and positional row diff",
   "where to read it": "proof_b row_diff",
   "varies as expected": "THIS IS THE QUESTION THE RUN ASKS. A zero is reported as the unscorable "
                         "shape of Rule 2 and never as 'the defect is harmless'",
   "evidence": "`cf.plan_state` -> `d.chosen` -> SessionAction or MATERIALIZE removal"},
 ],
 "step2b_switch_reaches_a_decision": (
  "Recorded as switch_arrival in a counted cell, which is excluded from every digest comparison: "
  "the class and name of each arm instance built, whether the switch is in its INSTANCE dict, its "
  "repr and its type, and the memoised `_qcache_key_fix_resolved`, which is written only by "
  "`_queued_behind` and is therefore the READ. An ON cell whose arrival says NOT READ has not run "
  "the mechanism and its null would be an ABSENT LINK, not a negative."),
 "step3_one_unit": (
  "Two readings. step3_isolated_key_trace is the mechanism in isolation, hand-checkable: the same "
  "arm asked twice at now_s 10.0 and 11.0, with the key printed each time, and an address-reuse "
  "trial in which a freed Observation's address is deliberately reoccupied. "
  "stale_hit_traces_from_that_wrapped_cell is the same thing inside a cell: up to five stale hits "
  "in full, with the reading period, the period that wrote the entry, the gap between them, and "
  "each row returned to `_harm_warm` with the slack_s computed from the other period's now_s."),
 "step4_negative_control": "step4_negative_control, on covex-v6-base at seed 4; see its `why`.",
 "step5_alternative_explanations": [
  ("A ZERO decision delta could be produced by (a) the stale value being priced but never "
   "crossing a margin in plan_state, or (b) the switch never arriving. (b) is excluded by "
   "step2b's switch_arrival; (a) is the remaining explanation and is exactly the UNSCORABLE shape "
   "of Rule 2, so a zero is reported as inconclusive-unscorable and not as a real negative."),
  ("A NON-ZERO delta could be produced by (a) the address key aliasing across periods [the "
   "claimed mechanism] or (b) some other difference between the two runs. (b) is excluded by "
   "construction for the within-arm comparison: the two cells differ in one expression, the OFF "
   "branch is byte-identical to the committed code, and the OFF side reproduces the committed "
   "digest."),
  ("A NON-ZERO CROSS-ARM delta that collapses under the fix could be produced by (a) the address "
   "key aliasing differently under two different allocation histories [the claimed mechanism] or "
   "(b) the two arms genuinely differing in policy. (b) is constrained for the pair used here "
   "only to the extent that covex-v6-state-shares-off is the DECLARED Step-4 collapse of "
   "covex-v6-state-uo; if the pair still differs with the switch ON, (b) is the live explanation "
   "and the pair proves nothing about the key."),
 ],
}

def _roots(root: str) -> List[str]:
    live2 = os.path.join(root, "experiments/orchestration/live2")
    return [live2, os.path.join(live2, "fleet"), os.path.join(live2, "v5"),
            os.path.join(live2, "hybrid"), os.path.join(live2, "tests"),
            os.path.join(root, "experiments/orchestration"),
            os.path.join(root, "experiments/orchestration/baselines"),
            os.path.join(root, "experiments/orchestration/sim"),
            os.path.join(root, "experiments/lib")]


def _path_in(root: str) -> None:
    for p in reversed(_roots(root)):
        if p not in sys.path:
            sys.path.insert(0, p)


def _loadavg() -> List[float]:
    with open("/proc/loadavg") as fh:
        return [float(x) for x in fh.read().split()[:3]]


def committed_digests() -> Dict[str, Dict[str, Any]]:
    """The before-the-change values every OFF-path digest here is audited against."""
    doc = json.loads(COMMITTED.read_text())
    out = {}
    for r in doc.get("arms", []):
        out[r["arm"]] = {"digest": r["before"]["digest"], "rows": r["before"]["rows"]}
    return {"source": str(COMMITTED.relative_to(REPO)), "sha": doc.get("_before_sha"),
            "cell": doc.get("_cell"), "by_arm": out}


# ---------------------------------------------------------------------------------------------
# the switch scope proof: no cell, no workload, just the declared shape
# ---------------------------------------------------------------------------------------------
def switch_tests(root: str) -> Dict[str, Any]:
    _path_in(root)
    import arms_v6state as VS

    out: Dict[str, Any] = {"switch_attr": VS.QCACHE_KEY_FIX_SWITCH, "checks": []}

    def rec(name: str, got: Any, want: Any) -> None:
        out["checks"].append({"check": name, "got": got, "want": want, "pass": got == want})

    rec("switch name", VS.QCACHE_KEY_FIX_SWITCH, SWITCH)

    class Bare:
        pass

    class ClassOn:
        live2_qcache_key_fix = True

    class ClassOff:
        live2_qcache_key_fix = False

    rec("absent on instance and class -> False", VS.qcache_key_fix_enabled(Bare()), False)
    inst_on = Bare()
    setattr(inst_on, SWITCH, True)
    rec("instance True -> True", VS.qcache_key_fix_enabled(inst_on), True)
    rec("harmless class default False -> False", VS.qcache_key_fix_enabled(ClassOff()), False)
    a = ClassOn()
    a.live2_qcache_key_fix = False
    rec("instance OFF overrides class ON -> False", VS.qcache_key_fix_enabled(a), False)
    try:
        VS.qcache_key_fix_enabled(ClassOn())
        rec("truthy CLASS attribute raises", "no raise", "QCacheKeyFixSwitchError")
    except VS.QCacheKeyFixSwitchError as exc:
        rec("truthy CLASS attribute raises", "QCacheKeyFixSwitchError", "QCacheKeyFixSwitchError")
        out["raise_message"] = str(exc)

    # the registered arms must not declare the switch anywhere in their class chain
    import arms as A
    declared = []
    for nm in RUNG2_ARMS + IDENTITY_ARMS:
        try:
            arm = A.ARMS[nm]()
        except Exception as exc:                                              # noqa: BLE001
            declared.append({"arm": nm, "constructed": False, "error": str(exc)[:200]})
            continue
        chain = [k.__name__ for k in type(arm).__mro__
                 if SWITCH in getattr(k, "__dict__", {})]
        declared.append({"arm": nm, "constructed": True,
                         "switch_in_instance_dict": SWITCH in vars(arm),
                         "classes_declaring_switch": chain,
                         "enabled": VS.qcache_key_fix_enabled(arm)})
    out["registered_arms"] = declared
    out["no_registered_arm_enables_the_switch"] = all(
        (not d.get("enabled", False)) for d in declared)
    out["pass"] = (all(c["pass"] for c in out["checks"])
                   and out["no_registered_arm_enables_the_switch"])
    return out


def key_trace(root: str) -> List[Dict[str, Any]]:
    """CLAUDE.md Step 3, the mechanism in isolation and hand-checkable.

    No workload and no cell. The same arm is asked twice, at now_s 10.0 and then 11.0, and the key
    it stored is printed each time. Then a freed Observation's address is deliberately reoccupied
    and the arm is asked again at a DIFFERENT now_s, to see whether the previous period's cached
    list comes back. One pass with the switch off, one with it on.
    """
    _path_in(root)
    import arms as A
    import arms_v6state as VS

    class Obs:
        def __init__(self, epoch: str, now: float) -> None:
            self.epoch = epoch
            self.now_s = now
            self.recall = ()

    out = []
    for want in (False, True):
        arm = A.ARMS["covex-v6-state-uo"]()
        if want:
            setattr(arm, SWITCH, True)
        arm._queued_behind(Obs("e1", 10.0), "sX")
        k1 = arm._q_cache_key
        arm._queued_behind(Obs("e1", 11.0), "sX")
        k2 = arm._q_cache_key
        row = {"switch": want,
               "resolved_and_read_by_queued_behind":
                   arm.__dict__.get("_qcache_key_fix_resolved"),
               "key_at_now_s_10": repr(k1), "key_at_now_s_11": repr(k2),
               "key_is_a_memory_address": isinstance(k1, int),
               "key_changed_between_the_two_periods": k1 != k2}
        arm2 = A.ARMS["covex-v6-state-uo"]()
        if want:
            setattr(arm2, SWITCH, True)
        ob = Obs("e1", 20.0)
        addr = id(ob)
        arm2._queued_behind(ob, "sX")
        planted = [{"session_id": "sOTHER", "req_id": "r1"}]
        arm2._q_cache = list(planted)
        del ob
        hit = None
        tries = 0
        for _ in range(20000):
            cand = Obs("e1", 21.0)
            tries += 1
            if id(cand) == addr:
                hit = (arm2._queued_behind(cand, "sX") == planted)
                break
            del cand
        row.update(address_reuse_reproduced=(hit is not None),
                   tries_to_reoccupy_the_address=tries,
                   the_previous_periods_list_came_back=hit)
        out.append(row)
    return out


# ---------------------------------------------------------------------------------------------
# one dry cell
# ---------------------------------------------------------------------------------------------
COUNTS_INIT = {"calls": 0, "hits": 0, "misses": 0, "stale_hits": 0, "fresh_hits": 0,
               "distinct_keys": 0, "periods_seen": 0,
               "stale_hits_cache_nonempty": 0, "stale_hits_cache_empty": 0,
               "stale_hits_returned_nonempty": 0, "stale_hits_recall_set_changed": 0}
# CLAUDE.md Step 3: the first few stale hits are recorded in full, so one unit of the mechanism is
# readable by hand instead of only summarised by a count.
MAX_TRACES = 5


def _install_counter(VS: Any, stats: Dict[str, int],
                     traces: Optional[List[Dict[str, Any]]] = None) -> None:
    """Count stale hits WITHOUT changing the key. Never installed in a digest cell."""
    orig = VS.V6StateArm._queued_behind
    owner: Dict[Any, Tuple[Any, Tuple, int]] = {}
    keys: set = set()
    periods: set = set()

    def sig(obs: Any) -> Tuple:
        return tuple((str(q.query_id), int(getattr(q, "readiness_tokens", 0) or 0),
                      str(q.session_id), float(q.deadline_s))
                     for q in (getattr(obs, "recall", None) or ()))

    def wrapped(self, obs, session_id):
        stats["calls"] += 1
        period = (str(getattr(obs, "epoch", "")), float(getattr(obs, "now_s", -1.0)))
        periods.add(period)
        stats["periods_seen"] = len(periods)
        k = self.__dict__.get("_q_cache_key")
        here = id(obs)
        keys.add(here)
        stats["distinct_keys"] = len(keys)
        if k is not None and k == here:
            stats["hits"] += 1
            own = owner.get(here)
            if own is not None and own[0] != period:
                stats["stale_hits"] += 1
                cached = list(self.__dict__.get("_q_cache") or ())
                if cached:
                    stats["stale_hits_cache_nonempty"] += 1
                else:
                    stats["stale_hits_cache_empty"] += 1
                if own[1] != sig(obs):
                    stats["stale_hits_recall_set_changed"] += 1
                returned = [r for r in cached if r["session_id"] != session_id]
                if returned:
                    stats["stale_hits_returned_nonempty"] += 1
                if traces is not None and returned and len(traces) < MAX_TRACES:
                    traces.append({
                        "arm": getattr(self, "name", None),
                        "asking_session_id": str(session_id),
                        "period_now_s_reading": period[1],
                        "period_now_s_that_wrote_the_entry": own[0][1],
                        "epoch_reading": period[0], "epoch_that_wrote": own[0][0],
                        "seconds_between_the_two_periods": round(period[1] - own[0][1], 6),
                        "address_used_as_the_key": here,
                        "recall_set_changed_between_them": own[1] != sig(obs),
                        "cached_rows": len(cached),
                        "returned_to_harm_warm": len(returned),
                        "returned_rows": [
                            {"req_id": r["req_id"], "session_id": r["session_id"],
                             "engine_s": r["engine_s"],
                             "slack_s_from_the_OTHER_period": r["slack_s"]}
                            for r in returned[:4]],
                        "note": ("each slack_s above is deadline_s - now_s with now_s from the "
                                 "period that WROTE the entry, not the period reading it")})
            else:
                stats["fresh_hits"] += 1
        else:
            stats["misses"] += 1
        out = orig(self, obs, session_id)
        owner[id(obs)] = (period, sig(obs), len(self.__dict__.get("_q_cache") or ()))
        return out

    VS.V6StateArm._queued_behind = wrapped


STAT_KEYS = ("decisions", "state_decisions", "state_chosen_HOLD_BACK", "state_chosen_TOUCH",
             "state_chosen_WARM", "state_chosen_KEEP", "state_chosen_SLICE",
             "state_touch_emitted", "state_hold_back_enacted",
             "harm_warm_priced", "harm_warm_nonzero", "harm_warm_milli_sum",
             "harm_warm_max_milli", "harm_warm_capped", "harm_warm_no_queue",
             "harm_warm_unpriced")


def one_cell(root: str, arm: str, seed: int, fix: bool, count: bool,
             out_path: Optional[str]) -> Dict[str, Any]:
    _path_in(root)
    t0 = time.time()
    load_start = _loadavg()

    import arms as A
    import arms_v6state as VS
    import arm_names_v6 as N
    import arms_v6fair as VF
    for mod in (VS, VF, N):
        fn = getattr(mod, "register", None)
        if fn is not None:
            fn()
    if arm not in A.ARMS:
        return {"arm": arm, "error": "not registered"}

    switch_present = hasattr(VS, "QCACHE_KEY_FIX_SWITCH")
    if fix and not switch_present:
        return {"arm": arm, "error": "this tree has no D188 switch; --fix on is impossible"}

    # THE SWITCH IS SET ON THE ARM INSTANCE, at construction, and never on a class.
    # THE FACTORY IS WRAPPED ONLY WHERE A WRAP CANNOT MATTER: when the switch must be set, or in a
    # counted cell, which is never compared with a digest. An OFF digest cell is audited against a
    # value committed BEFORE this change, so it constructs the arm through the registry's own entry
    # untouched; an extra closure and a retained reference are exactly what a byte-identity proof
    # exists to catch, and they must not sit on the side that is supposed to be unchanged.
    built: List[Any] = []
    if fix or count:
        base = A.ARMS[arm]

        def mk(_b=base, _fix=fix, **kw):
            a = _b(**kw)
            if _fix:
                setattr(a, SWITCH, True)
            built.append(a)
            return a

        A.ARMS[arm] = mk

    import cf_instrument as CI
    patched = []
    for nm in dir(CI):
        obj = getattr(CI, nm)
        if isinstance(obj, type) and hasattr(obj, "over_budget"):
            obj.over_budget = lambda self, budget_ms=None: False
            patched.append(nm)

    stats_counter = dict(COUNTS_INIT)
    traces: List[Dict[str, Any]] = []
    if count:
        _install_counter(VS, stats_counter, traces)

    import test_hybrid as TH
    kw = {k: v for k, v in POSTED.items()
          if k in ("dashcam_format", "robot_upload", "robot_reask_mean_s")}
    rows, st = TH.dry(arm, seed, CELL["n"], run_s=CELL["run_s"], ratio=POSTED["ratio"],
                      robot_question_set=POSTED["robot_question_set"],
                      ss_question_set=POSTED["ss_question_set"], **kw)
    rows = list(rows or [])
    rr = [{k: v for k, v in r.items() if k != "arm_version"} for r in rows]
    digest = hashlib.sha256(json.dumps(rr, sort_keys=True, separators=(",", ":"),
                                       default=float).encode()).hexdigest()[:16]
    st = dict(st or {})
    ru = resource.getrusage(resource.RUSAGE_SELF)
    res = {"arm": arm, "seed": seed, "fix": bool(fix), "counted": bool(count),
           "root": root, "switch_present_in_tree": switch_present,
           "digest": digest, "rows": len(rows), "workload": "posted",
           "n": CELL["n"], "run_s": CELL["run_s"],
           "arm_stats": {k: st.get(k) for k in STAT_KEYS},
           "cutoff_patched_off_on": patched,
           "host": {"loadavg_start": load_start, "loadavg_end": _loadavg(),
                    "cpu_user_s": round(ru.ru_utime, 2), "cpu_sys_s": round(ru.ru_stime, 2),
                    "wall_s": round(time.time() - t0, 2), "pid": os.getpid()}}
    if count:
        res["qcache_counts"] = dict(stats_counter)
        res["qcache_stale_hit_traces"] = traces
        # Step 2b, recorded ONLY in a counted cell. A counted cell is already excluded from every
        # digest comparison because the wrapper perturbs the address reuse it counts, so retaining
        # the arm instances here cannot contaminate a digest. `_qcache_key_fix_resolved` is written
        # only by `_queued_behind`, so its presence IS the read and its value is the branch taken.
        res["switch_arrival"] = [{
            "class": type(x).__name__, "arm_name": getattr(x, "name", None),
            "in_instance_dict": SWITCH in vars(x),
            "declared_value": repr(vars(x).get(SWITCH)),
            "declared_type": type(vars(x).get(SWITCH)).__name__,
            "resolved_and_read_by_queued_behind":
                vars(x).get("_qcache_key_fix_resolved", "NOT READ"),
        } for x in built]
    if out_path:
        Path(out_path).write_text(json.dumps(res) + "\n")
        Path(out_path + ".rows.json").write_text(
            json.dumps(rr, separators=(",", ":"), default=float))
    return res


# ---------------------------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------------------------
def row_diff(a: Path, b: Path) -> Dict[str, Any]:
    """Setwise AND positional diff of two decision-row lists, with the first differing row."""
    if not (a.exists() and b.exists()):
        return {"available": False}
    ra = json.loads(a.read_text())
    rb = json.loads(b.read_text())
    ka = [json.dumps(x, sort_keys=True, separators=(",", ":")) for x in ra]
    kb = [json.dumps(x, sort_keys=True, separators=(",", ":")) for x in rb]
    from collections import Counter
    ca, cb = Counter(ka), Counter(kb)
    only_a = sum((ca - cb).values())
    only_b = sum((cb - ca).values())
    pos = [i for i in range(min(len(ka), len(kb))) if ka[i] != kb[i]]
    pos_diff = len(pos) + abs(len(ka) - len(kb))
    first = None
    if pos:
        i = pos[0]
        first = {"index": i, "off": json.loads(ka[i]), "on": json.loads(kb[i])}
    elif len(ka) != len(kb):
        longer, idx = (ka, len(kb)) if len(ka) > len(kb) else (kb, len(ka))
        first = {"index": idx, "only_in": "off" if longer is ka else "on",
                 "row": json.loads(longer[idx])}
    return {"available": True, "rows_off": len(ka), "rows_on": len(kb),
            "setwise_rows_only_off": only_a, "setwise_rows_only_on": only_b,
            "setwise_differing_rows": only_a + only_b,
            "positional_differing_rows": pos_diff,
            "identical_setwise": (only_a == 0 and only_b == 0),
            "identical_positionally": (pos_diff == 0),
            "first_differing_row": first}


def _subcall(args: List[str]) -> Any:
    """Run one of this file's own read-only modes in a fresh process and return its JSON."""
    cmd = [sys.executable, "-I", str(Path(__file__).resolve())] + args
    p = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(p.stdout)
    except Exception as exc:                                                  # noqa: BLE001
        return {"error": "%s: %s" % (exc, ((p.stderr or "").strip().splitlines() or [""])[-1])}


def _spawn(root: str, arm: str, seed: int, fix: bool, count: bool, out: str,
           timeout: int) -> Dict[str, Any]:
    cmd = ["nice", "-n", "10", sys.executable, "-I", str(Path(__file__).resolve()),
           "--one-cell", "--root", root, "--arm", arm, "--seed", str(seed),
           "--fix", "on" if fix else "off", "--out", out]
    if count:
        cmd.append("--count")
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"arm": arm, "error": "timeout after %ds" % timeout}
    if Path(out).exists():
        return json.loads(Path(out).read_text())
    tail = ((p.stderr or "").strip().splitlines() or ["no output"])[-1]
    return {"arm": arm, "seed": seed, "fix": fix, "error": tail[:400]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--one-cell", action="store_true")
    ap.add_argument("--switch-tests", action="store_true")
    ap.add_argument("--key-trace", action="store_true")
    ap.add_argument("--root")
    ap.add_argument("--arm")
    ap.add_argument("--seed", type=int, default=4)
    ap.add_argument("--fix", choices=("on", "off"), default="off")
    ap.add_argument("--count", action="store_true")
    ap.add_argument("--before-root")
    ap.add_argument("--after-root")
    ap.add_argument("--base-sha")
    ap.add_argument("--work")
    ap.add_argument("--seeds", default="4")
    ap.add_argument("--jobs", type=int, default=12)
    ap.add_argument("--timeout", type=int, default=14400)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    if a.switch_tests:
        print(json.dumps(switch_tests(a.root), indent=1))
        return 0
    if a.key_trace:
        print(json.dumps(key_trace(a.root), indent=1))
        return 0
    if a.one_cell:
        if a.seed not in ALLOWED_SEEDS:
            print("seed %d not allowed" % a.seed, file=sys.stderr)
            return 2
        r = one_cell(a.root, a.arm, a.seed, a.fix == "on", a.count, a.out)
        print(json.dumps(r))
        return 0 if not r.get("error") else 1

    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    seeds = [int(s) for s in a.seeds.split(",") if s.strip()]
    for s in seeds:
        if s not in ALLOWED_SEEDS:
            print("seed %d not allowed" % s, file=sys.stderr)
            return 2
    com = committed_digests()

    jobs: List[Tuple[str, str, str, int, bool, bool]] = []
    # (tag, root, arm, seed, fix, count)
    for arm in IDENTITY_ARMS:
        jobs.append(("ident_after", a.after_root, arm, seeds[0], False, False))
    for s in seeds:
        for arm in RUNG2_ARMS:
            jobs.append(("r2_off", a.after_root, arm, s, False, False))
            jobs.append(("r2_on", a.after_root, arm, s, True, False))
    for arm in RUNG2_ARMS:
        jobs.append(("r2_count_off", a.after_root, arm, seeds[0], False, True))
        jobs.append(("r2_count_on", a.after_root, arm, seeds[0], True, True))
    for s in seeds:
        for arm in CROSS_ARMS:
            for tag, fx in (("r2_off", False), ("r2_on", True)):
                if (tag, arm, s) not in [(j[0], j[2], j[3]) for j in jobs]:
                    jobs.append((tag, a.after_root, arm, s, fx, False))
    jobs.append(("negctrl_on", a.after_root, NEGCTRL_ARM, seeds[0], True, False))

    def out_for(tag: str, arm: str, seed: int) -> str:
        return str(work / ("%s__%s__s%d.json" % (tag, arm, seed)))

    t0 = time.time()
    load_start = _loadavg()
    res: Dict[Tuple[str, str, int], Dict[str, Any]] = {}

    def run(job):
        tag, root, arm, seed, fix, count = job
        o = out_for(tag, arm, seed)
        if Path(o).exists() and Path(o + ".rows.json").exists():
            r = json.loads(Path(o).read_text())
        else:
            r = _spawn(root, arm, seed, fix, count, o, a.timeout)
        print("%-14s %-30s s%d digest=%-18s rows=%-7s %s" % (
            tag, arm, seed, r.get("digest"), r.get("rows"),
            ("ERROR " + str(r.get("error"))) if r.get("error") else ""), flush=True)
        return (tag, arm, seed), r

    with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as ex:
        for k, r in ex.map(run, jobs):
            res[k] = r

    # ---- proof (a): OFF-path byte identity, each audited against a committed value -----------
    ident = []
    for arm in IDENTITY_ARMS:
        r = res.get(("ident_after", arm, seeds[0]), {})
        c = com["by_arm"].get(arm)
        row = {"arm": arm, "with_switch_off": {k: r.get(k) for k in ("digest", "rows", "error")},
               "committed_before_the_change": c,
               "committed_source": com["source"], "committed_sha": com["sha"]}
        row["identical_to_committed"] = bool(
            c and r.get("digest") == c["digest"] and r.get("rows") == c["rows"])
        ident.append(row)
    moved = [r["arm"] for r in ident if not r["identical_to_committed"]]

    # attribution pass: anything that moved is re-run on the UNPATCHED tree, so a move by an
    # intervening commit cannot be read as a move by this change
    attrib = []
    if moved:
        bjobs = [("ident_before", a.before_root, arm, seeds[0], False, False) for arm in moved]
        with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as ex:
            for k, r in ex.map(run, bjobs):
                res[k] = r
        for arm in moved:
            b = res.get(("ident_before", arm, seeds[0]), {})
            af = res.get(("ident_after", arm, seeds[0]), {})
            c = com["by_arm"].get(arm)
            attrib.append({
                "arm": arm, "unpatched_origin_main": {k: b.get(k) for k in ("digest", "rows")},
                "patched_switch_off": {k: af.get(k) for k in ("digest", "rows")},
                "committed": c,
                "this_change_moved_it": b.get("digest") != af.get("digest"),
                "a_commit_since_the_committed_run_moved_it": (
                    c is not None and b.get("digest") != c["digest"])})

    # ---- proof (b): rung-2 dry decision deltas, switch ON against switch OFF -----------------
    deltas = []
    for s in seeds:
        for arm in RUNG2_ARMS:
            off = res.get(("r2_off", arm, s), {})
            on = res.get(("r2_on", arm, s), {})
            cnt = res.get(("r2_count_off", arm, seeds[0]), {}) if s == seeds[0] else {}
            d = row_diff(Path(out_for("r2_off", arm, s) + ".rows.json"),
                         Path(out_for("r2_on", arm, s) + ".rows.json"))
            deltas.append({
                "arm": arm, "seed": s,
                "off": {k: off.get(k) for k in ("digest", "rows", "error")},
                "on": {k: on.get(k) for k in ("digest", "rows", "error")},
                "digest_identical": off.get("digest") == on.get("digest"),
                "row_diff": d,
                "harm_warm_off": (off.get("arm_stats") or {}).get("harm_warm_nonzero"),
                "harm_warm_on": (on.get("arm_stats") or {}).get("harm_warm_nonzero"),
                "arm_stats_off": off.get("arm_stats"),
                "arm_stats_on": on.get("arm_stats"),
                "stale_hits_from_a_separate_WRAPPED_off_cell": cnt.get("qcache_counts"),
                "stale_hit_traces_from_that_wrapped_cell": cnt.get("qcache_stale_hit_traces"),
                "switch_arrival_from_a_separate_WRAPPED_on_cell": (
                    res.get(("r2_count_on", arm, seeds[0]), {}).get("switch_arrival")
                    if s == seeds[0] else None),
                "stale_hits_from_a_separate_WRAPPED_on_cell": (
                    res.get(("r2_count_on", arm, seeds[0]), {}).get("qcache_counts")
                    if s == seeds[0] else None),
            })

    # ---- proof (c): the CROSS-ARM claim, tested rather than accepted ------------------------
    cross = []
    for s in seeds:
        for left, right in CROSS_ARM_PAIRS:
            row: Dict[str, Any] = {"pair": [left, right], "seed": s}
            for mode in ("off", "on"):
                tag = "r2_" + mode
                row[mode] = {
                    "left_digest": res.get((tag, left, s), {}).get("digest"),
                    "left_rows": res.get((tag, left, s), {}).get("rows"),
                    "right_digest": res.get((tag, right, s), {}).get("digest"),
                    "right_rows": res.get((tag, right, s), {}).get("rows"),
                    "diff": row_diff(Path(out_for(tag, left, s) + ".rows.json"),
                                     Path(out_for(tag, right, s) + ".rows.json"))}
                row[mode]["identical"] = (
                    row[mode]["left_digest"] is not None
                    and row[mode]["left_digest"] == row[mode]["right_digest"])
            row["reconciliation_confirmed"] = bool(
                (not row["off"]["identical"]) and row["on"]["identical"])
            cross.append(row)

    doc = {
        "_what": ("D188 (2): the `_queued_behind` cache-key fix prepared behind an OFF-by-default "
                  "arm-scoped switch, with (a) its byte-identity proof on the non-rung-2 arms "
                  "against committed values and (b) a dry measurement of how many rung-2 "
                  "decisions it changes with the switch ON."),
        "_ruling": ("The fix is NOT applied to any cell tonight. No registered arm declares the "
                    "switch; the ON cells below construct the arm and set the INSTANCE attribute "
                    "inside the measuring process only."),
        "_switch": {"name": SWITCH, "default": False,
                    "scope": "arm-scoped INSTANCE attribute; a truthy CLASS attribute raises",
                    "pattern_copied_from": ["release_recheck.arm_enables",
                                            "share_admission.arm_enables"]},
        "_base_sha": a.base_sha, "_before_root": a.before_root, "_after_root": a.after_root,
        "_cell": dict(CELL, **POSTED), "_seeds": seeds,
        "_protocol": {
            "one_dry_cell_per_process": True,
            "cf_instrument_over_budget_patched_off": True,
            "digest_cells_are_unwrapped": True,
            "counting_wrapper_run_in_its_own_cell": True,
            "digest_recipe": ("sha256(json.dumps(rows_without_arm_version, sort_keys=True, "
                              "separators=(',',':'), default=float))[:16]"),
            "concurrency": a.jobs, "cores": os.cpu_count(),
            "loadavg_driver_start": load_start, "loadavg_driver_end": _loadavg(),
            "wall_s": round(time.time() - t0, 2)},
        "_register": (
            "A DRY REPLAY MEASURES DRY ALLOCATION PATTERNS. The stale-hit counts and the decision "
            "deltas below are an INDICATION of live exposure, NOT a measurement of it: a live run "
            "has a real backend, I/O threads and a different allocation history, and nothing here "
            "bounds that. The counting wrapper itself allocates, so its counts are taken in a "
            "separate cell from any digest and perturb the very reuse they count."),
        "_committed_reference": {"source": com["source"], "sha": com["sha"], "cell": com["cell"]},
        "proof_a_offswitch_byte_identity": ident,
        "proof_a_moved_arms_attributed": attrib,
        "proof_b_rung2_dry_decision_deltas": deltas,
        "proof_c_cross_arm_claim": cross,
        "step4_negative_control": {
            "arm": NEGCTRL_ARM,
            "why": ("this arm never enters V6StateArm, so the key cannot reach a decision in it; "
                    "with the switch ON it must still give its own OFF digest and its committed "
                    "value"),
            "switch_on": {k: res.get(("negctrl_on", NEGCTRL_ARM, seeds[0]), {}).get(k)
                          for k in ("digest", "rows", "error")},
            "switch_off": {k: res.get(("ident_after", NEGCTRL_ARM, seeds[0]), {}).get(k)
                           for k in ("digest", "rows")},
            "committed": com["by_arm"].get(NEGCTRL_ARM),
            "collapses": (res.get(("negctrl_on", NEGCTRL_ARM, seeds[0]), {}).get("digest")
                          == (com["by_arm"].get(NEGCTRL_ARM) or {}).get("digest")),
        },
        "step3_isolated_key_trace": _subcall(["--key-trace", "--root", a.after_root]),
        "switch_scope_proof": _subcall(["--switch-tests", "--root", a.after_root]),
        "_mechanism_verification": MECHANISM,
    }
    doc["verdict_proof_a"] = (
        "PASS: all %d arms reproduce their committed digest with the switch OFF." % len(ident)
        if not moved else
        "STOP: %d of %d arms do not reproduce their committed digest with the switch OFF: %s"
        % (len(moved), len(ident), moved))
    changed = [("%s s%d" % (d["arm"], d["seed"])) for d in deltas
               if not d["digest_identical"]]
    doc["verdict_proof_b"] = (
        "the switch ON changes NO decision row on any rung-2 cell measured here"
        if not changed else
        "the switch ON changes decisions on %d of %d rung-2 cells: %s"
        % (len(changed), len(deltas), changed))

    doc["verdict_proof_c"] = "; ".join(
        "%s vs %s s%d: OFF %s, ON %s -> reconciliation %s" % (
            r["pair"][0], r["pair"][1], r["seed"],
            "identical" if r["off"]["identical"] else ("%s differing rows positionally"
                                                       % r["off"]["diff"].get(
                                                           "positional_differing_rows")),
            "identical" if r["on"]["identical"] else ("%s differing rows positionally"
                                                      % r["on"]["diff"].get(
                                                          "positional_differing_rows")),
            "CONFIRMED" if r["reconciliation_confirmed"] else "NOT confirmed")
        for r in cross) or "no cross-arm pair measured"

    sys.path.insert(0, str(REPO / "experiments/lib"))
    try:
        from _provenance import stamp
        doc["_provenance"] = stamp(script="d188_qcache_key_fix_proofs.py",
                                   model="n/a (policy proof, dry cells, no server)",
                                   device="flash (CPU)", n=len(jobs))
        # the stamp records the REPO's HEAD, which is not the ref these trees were exported from
        doc["_provenance"]["tree_exported_from_ref"] = a.base_sha
    except Exception as exc:                                                  # noqa: BLE001
        doc["_provenance"] = {"git_commit": a.base_sha, "script": "d188_qcache_key_fix_proofs.py",
                              "note": "stamp unavailable: %s" % exc}

    dest = Path(a.out) if a.out else (
        REPO / "results/orchestration/live2/frozen_test/d188_qcache_key_fix_proofs.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(doc, indent=1) + "\n")
    print(doc["verdict_proof_a"])
    print(doc["verdict_proof_b"])
    print(doc["verdict_proof_c"])
    print("wrote", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
