#!/usr/bin/env python3
"""D179 (6a): with both share-admission switches OFF, the share-admission build changes NO other
arm's decisions. Before/after digest equality per arm, one dry cell per process.

WHAT IS COMPARED. Two CLEAN git worktrees, named by `--before-root` and `--after-root`, are run
with identical setup and identical posted workload knobs, and the decision log of each arm is
hashed. The claim is byte-equality of the hashed log, so an arm whose digest moves is a D179 STOP.

WHY NOT THE LIVE WORKTREE. /tmp/claude-1001/mapwt sits at the after commit but carries session A's
UNCOMMITTED edits, among them v5/cf_objective.py, which is policy and does move decisions. Running
the after side from it would have attributed those edits to D179. Both sides here are checkouts of
a commit with a clean `git status`, and the shas are recorded in the output.

ONE DRY CELL PER PROCESS. A second dry run inside one process does not reproduce the first
(covex-v6-state gave 15,871 rows then 16,109, with state_decisions moving 44,300 to 45,337; cause
open, ruled out are the planner wall-clock limit, PYTHONHASHSEED and the registration context).
Separate processes with identical setup DO reproduce exactly, so every digest here is one process.

WHY THE WALL-CLOCK CUTOFF IS PATCHED OFF. cf_instrument's `over_budget` compares elapsed
perf_counter_ns against budget_ms, so under machine load the planner abandons to base and the
decision log becomes a property of the load rather than of the arm. These cells are run CONCURRENTLY,
so the cutoff is patched off on both sides of every comparison. Live cells keep it ON (D99 (3)).

HOST LOAD is recorded per process as D115 (2) requires: /proc/loadavg at the start and the end of
each cell plus that process's own user+system CPU seconds, so a digest can be read against the load
it was produced under and a load-sensitive result cannot be mistaken for an arm property.

Usage:
  one cell:  d179_offswitch_digest_proofs.py --one-cell --root <worktree> --arm <arm> [--seed 4]
  driver:    d179_offswitch_digest_proofs.py --before-root <wt> --after-root <wt> \
                 --before-sha <sha> --after-sha <sha> [--jobs 18] [--all-arms] [--out <path>]
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

# the posted workload knobs (user addendum). test_hybrid.dry defaults to oneframe dashcam bodies,
# batch-30s upload and no re-asks, which is a DIFFERENT workload and would measure the wrong thing.
POSTED = dict(ratio="40:40:20", robot_question_set="lh_req", ss_question_set="ss2",
              dashcam_format="epg", robot_upload="per-frame", robot_reask_mean_s=30.0)
CELL = dict(n=16, run_s=1200.0, seed=4)

# D179 (6a) names base, rules and all baselines. These are the ones the gate is stated over; with
# --all-arms every registered arm is tested on top of these.
REQUIRED_ARMS = (
    "covex-v6-base", "covex-v6-rules", "covex-v6-state-uo", "v5-rules-2",
    "hybrid-F-lhreq-noc3", "b7-edf-feasibility", "always-cloud-fcfs", "edf", "llf",
    "mooncake", "attentionstore-prefetch", "simplestream", "querystream-proactive",
    "warm-all-lru", "confidence-cascade", "eco-llm",
)
# the planner-bearing arms, run TWICE on the after side under the same parallel load so
# self-reproduction under load is checked and not assumed
PLANNER_ARMS = ("covex-v6-state-uo", "covex-v6-state-noprice")
ALLOWED_SEEDS = (0, 4, 5, 6, 7)


def _roots(root: str) -> List[str]:
    live2 = os.path.join(root, "experiments/orchestration/live2")
    return [live2, os.path.join(live2, "fleet"), os.path.join(live2, "v5"),
            os.path.join(live2, "hybrid"), os.path.join(live2, "tests"),
            os.path.join(root, "experiments/orchestration"),
            os.path.join(root, "experiments/orchestration/baselines"),
            os.path.join(root, "experiments/orchestration/sim"),
            os.path.join(root, "experiments/lib")]


def _loadavg() -> List[float]:
    with open("/proc/loadavg") as fh:
        return [float(x) for x in fh.read().split()[:3]]


def register_arms() -> Dict[str, Any]:
    """Import the registry and call every register() the gate is stated over. Reported so a run
    cannot silently test a smaller registry than it claims."""
    import arms as A
    pre = sorted(A.ARMS)
    import arm_names_v6 as N
    import arms_v6fair as VF
    import arms_v6state as VS
    for mod in (VS, VF, N):
        fn = getattr(mod, "register", None)
        if fn is not None:
            fn()
    return {"registry": A.ARMS, "n_at_import": len(pre),
            "n_after_register": len(A.ARMS),
            "added_by_register": sorted(set(A.ARMS) - set(pre))}


def scope_facts(before_root: str, after_root: str, before_sha: Optional[str],
                after_sha: Optional[str]) -> Dict[str, Any]:
    """What the two trees actually differ by, so a reader can tell a cleared gate from a vacuous
    one. A digest identity between two trees that differ only by an unimported module is TRUE and
    proves nothing about plumbing that is not in either tree."""
    def grep_count(root: str, pat: str) -> int:
        p = subprocess.run(["grep", "-rn", "--include=*.py", "-e", pat, root],
                           capture_output=True, text=True)
        return len([l for l in (p.stdout or "").splitlines() if l.strip()])

    def tracked_diff() -> List[str]:
        if not (before_sha and after_sha):
            return []
        p = subprocess.run(["git", "diff", "--name-only", before_sha, after_sha],
                           capture_output=True, text=True, cwd=str(REPO))
        return [l for l in (p.stdout or "").splitlines() if l.strip()]

    co = "experiments/orchestration/live2/coordinator.py"
    same_co = subprocess.run(["cmp", "-s", os.path.join(before_root, co),
                              os.path.join(after_root, co)]).returncode == 0
    out: Dict[str, Any] = {
        "tracked_files_changed_between_the_two_shas": tracked_diff(),
        "coordinator_py_byte_identical_across_the_two_sides": same_co,
        "share_admission_importers": {},
        "switch_name_references": {},
        "share_capacity_present": {},
    }
    for label, root in (("before", before_root), ("after", after_root)):
        out["share_admission_importers"][label] = grep_count(
            root, r"^\s*\(import share_admission\|from share_admission\)")
        out["switch_name_references"][label] = {
            "live2_share_admission": grep_count(root, "live2_share_admission"),
            "live2_release_recheck": grep_count(root, "live2_release_recheck")}
        out["share_capacity_present"][label] = os.path.exists(os.path.join(
            root, "experiments/orchestration/live2/share_capacity.py"))
    return out


def one_cell(root: str, arm: str, seed: int) -> Dict[str, Any]:
    for p in reversed(_roots(root)):
        if p not in sys.path:
            sys.path.insert(0, p)
    load_start = _loadavg()
    t0 = time.time()
    reg = register_arms()
    if arm not in reg["registry"]:
        return {"arm": arm, "error": "not registered", "registry_size": reg["n_after_register"]}

    import cf_instrument as CI
    patched = []
    for nm in dir(CI):
        obj = getattr(CI, nm)
        if isinstance(obj, type) and hasattr(obj, "over_budget"):
            obj.over_budget = lambda self, budget_ms=None: False
            patched.append(nm)

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
    ru = resource.getrusage(resource.RUSAGE_SELF)
    st = dict(st or {})
    return {"arm": arm, "seed": seed, "n": CELL["n"], "run_s": CELL["run_s"],
            "workload": "posted", "digest": digest, "rows": len(rows),
            "state_decisions": st.get("state_decisions"), "decisions": st.get("decisions"),
            "cutoff_patched_off_on": patched,
            "registry_size": reg["n_after_register"],
            "registry_added_by_register": reg["added_by_register"],
            "host": {"loadavg_start": load_start, "loadavg_end": _loadavg(),
                     "cpu_user_s": round(ru.ru_utime, 2), "cpu_sys_s": round(ru.ru_stime, 2),
                     "wall_s": round(time.time() - t0, 2), "pid": os.getpid()}}


def _spawn(root: str, arm: str, seed: int, timeout: int) -> Dict[str, Any]:
    cmd = ["nice", "-n", "10", sys.executable, str(Path(__file__).resolve()),
           "--one-cell", "--root", root, "--arm", arm, "--seed", str(seed)]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"arm": arm, "error": "timeout after %ds" % timeout}
    lines = [l for l in (p.stdout or "").splitlines() if l.startswith("{")]
    if not lines:
        tail = ((p.stderr or "").strip().splitlines() or ["no output"])[-1]
        return {"arm": arm, "error": tail[:400], "wall_s": round(time.time() - t0, 2)}
    return json.loads(lines[-1])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--one-cell", action="store_true")
    ap.add_argument("--root")
    ap.add_argument("--arm")
    ap.add_argument("--seed", type=int, default=CELL["seed"])
    ap.add_argument("--before-root")
    ap.add_argument("--after-root")
    ap.add_argument("--before-sha")
    ap.add_argument("--after-sha")
    ap.add_argument("--jobs", type=int, default=18)
    ap.add_argument("--arms", default=None, help="comma separated; default the D179 (6a) set")
    ap.add_argument("--all-arms", action="store_true")
    ap.add_argument("--timeout", type=int, default=10800)
    ap.add_argument("--sequential", action="store_true")
    ap.add_argument("--annotate", action="store_true",
                    help="recompute the structural scope facts from the two roots and merge them "
                         "into an existing --out JSON, without touching any digest")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.seed not in ALLOWED_SEEDS:
        print("seed %d is not in the allowed set %s" % (a.seed, ALLOWED_SEEDS), file=sys.stderr)
        return 2

    if a.one_cell:
        print(json.dumps(one_cell(a.root, a.arm, a.seed)))
        return 0

    if a.annotate:
        dest = Path(a.out)
        doc = json.loads(dest.read_text())
        doc["_scope"] = scope_facts(a.before_root, a.after_root, a.before_sha, a.after_sha)
        doc["_verdict_register"] = (
            "TRUE BUT VACUOUS at this after commit, and therefore an ABSENT LINK in the Step 2b "
            "sense, not a negative. The identity below is a real measurement and it is also "
            "guaranteed by the code: the only tracked difference between the two shas is the "
            "addition of share_admission.py, which NO module imports and which cannot even be "
            "imported at the after commit (it does `import share_capacity` and share_capacity.py "
            "is absent from that tree), while coordinator.py is byte-identical on both sides and "
            "neither switch name appears anywhere in either tree. The per-type work tracking and "
            "the switch plumbing that D179 (6a) exists to clear ARE NOT IN ANY REACHABLE COMMIT "
            "yet. This result therefore clears the interface commit only; the gate must be re-run "
            "against session A's plumbing commit before the shares cells are read against it.")
        doc["_positive_control"] = (
            "the digest DISCRIMINATES arms, so the identity is not an artefact of a degenerate "
            "hash: %d distinct digests across %d arms, row counts 11,955 to 46,931."
            % (len({r["before"]["digest"] for r in doc["arms"]}), len(doc["arms"])))
        sys.path.insert(0, str(REPO / "experiments/lib"))
        from _provenance import stamp
        doc["_provenance"] = stamp(script="d179_offswitch_digest_proofs.py",
                                   model="n/a (policy proof, dry cells, no server)",
                                   device="flash (CPU)", n=36, seed=a.seed)
        dest.write_text(json.dumps(doc, indent=1) + "\n")
        print("annotated", dest)
        return 0

    for p in reversed(_roots(a.after_root)):
        if p not in sys.path:
            sys.path.insert(0, p)
    reg = register_arms()
    if a.arms:
        arms = [s for s in a.arms.split(",") if s]
    elif a.all_arms:
        arms = sorted(reg["registry"])
    else:
        arms = list(REQUIRED_ARMS) + [x for x in PLANNER_ARMS if x not in REQUIRED_ARMS]

    # (label, root, arm). The planner arms get a SECOND after-side cell, under the same load.
    jobs: List[Tuple[str, str, str]] = []
    for arm in arms:
        jobs.append(("before", a.before_root, arm))
        jobs.append(("after", a.after_root, arm))
    for arm in PLANNER_ARMS:
        if arm in arms:
            jobs.append(("after_repeat", a.after_root, arm))

    conc = 1 if a.sequential else max(1, a.jobs)
    load_start = _loadavg()
    t0 = time.time()
    results: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def work(job):
        label, root, arm = job
        r = _spawn(root, arm, a.seed, a.timeout)
        r["side"] = label
        print("%-12s %-28s digest=%-17s rows=%s %s" % (
            label, arm, r.get("digest"), r.get("rows"),
            ("ERROR " + str(r.get("error"))) if r.get("error") else ""), flush=True)
        return (label, arm), r

    with ThreadPoolExecutor(max_workers=conc) as ex:
        for key, r in ex.map(work, jobs):
            results[key] = r

    per_arm = []
    for arm in arms:
        b, f = results.get(("before", arm), {}), results.get(("after", arm), {})
        rep = results.get(("after_repeat", arm))
        ok = (b.get("digest") is not None and b.get("digest") == f.get("digest")
              and b.get("rows") == f.get("rows"))
        row = {"arm": arm,
               "before": {k: b.get(k) for k in ("digest", "rows", "state_decisions", "error")},
               "after": {k: f.get(k) for k in ("digest", "rows", "state_decisions", "error")},
               "identical": bool(ok),
               "before_host": b.get("host"), "after_host": f.get("host")}
        if rep is not None:
            row["after_repeat"] = {k: rep.get(k) for k in
                                   ("digest", "rows", "state_decisions", "error")}
            row["after_self_reproduces_under_load"] = bool(
                f.get("digest") is not None and f.get("digest") == rep.get("digest")
                and f.get("rows") == rep.get("rows"))
            row["after_repeat_host"] = rep.get("host")
        per_arm.append(row)

    errored = [r["arm"] for r in per_arm
               if r["before"].get("error") or r["after"].get("error")]
    tested = [r for r in per_arm if r["arm"] not in errored]
    moved = [r["arm"] for r in tested if not r["identical"]]
    repro = [r for r in per_arm if "after_self_reproduces_under_load" in r]
    cpu = [(r["arm"], (r["before_host"] or {}).get("cpu_user_s"),
            (r["after_host"] or {}).get("cpu_user_s")) for r in per_arm]

    out = {
        "_what": ("D179 (6a): with live2_share_admission and live2_release_recheck both OFF, the "
                  "share-admission build changes no other arm's decisions"),
        "_before_sha": a.before_sha, "_after_sha": a.after_sha,
        "_before_root": a.before_root, "_after_root": a.after_root,
        "_cell": dict(CELL, **POSTED),
        "_protocol": {
            "one_dry_cell_per_process": True,
            "cf_instrument_over_budget_patched_off": True,
            "concurrency": conc, "sequential": bool(a.sequential),
            "cores": os.cpu_count(),
            "loadavg_driver_start": load_start, "loadavg_driver_end": _loadavg(),
            "wall_s": round(time.time() - t0, 2),
            "cpu_user_s_by_arm": cpu,
        },
        "_registry": {"n_at_import": reg["n_at_import"],
                      "n_after_register": reg["n_after_register"],
                      "added_by_register": reg["added_by_register"],
                      "n_arms_tested": len(tested), "arms_not_constructed": errored},
        "arms": per_arm,
        "planner_self_reproduction_under_load": [
            {"arm": r["arm"], "after": r["after"]["digest"],
             "after_repeat": r["after_repeat"]["digest"],
             "reproduces": r["after_self_reproduces_under_load"]} for r in repro],
    }
    if moved:
        out["verdict"] = ("STOP (D179 (6a) FAILS): %d of %d arms moved decisions with both "
                          "switches OFF: %s. The shares cells may not run until this is explained."
                          % (len(moved), len(tested), moved))
    else:
        out["verdict"] = ("PASS: all %d constructed arms give byte-identical decision digests "
                          "before and after, with both switches OFF." % len(tested))
    dest = Path(a.out) if a.out else (
        REPO / "results/orchestration/live2/frozen_test/d179_offswitch_digest_proofs.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1) + "\n")
    print(out["verdict"])
    print("wrote", dest)
    return 1 if moved else 0


if __name__ == "__main__":
    raise SystemExit(main())
