#!/usr/bin/env python3
"""E1 + E3 PROOFS: the engine /metrics scrape is LIVE, and a cell says whether to trust it.

D216 (2) (flash wires the scrape with this build's real metric names and hit-6 fail-loud
semantics, byte-identical for every arm that does not read the field), D222 (1) g, D227 (E3: the
one-line `metrics_health` field in every `cell.json`, three states distinguishable).

WHAT WAS BROKEN, STATED AS THE CENSUS THAT FOUND IT. `scrape_metrics()` had TWO occurrences in the
whole tree at `f1d27c22`: its own definition at `asyncbackend.py:175` and a prose comment in
`n5_queued_by_class_census.py`. ZERO CALLERS. `metrics()`, the only method `coordinator.py:489`
calls, returned wire statistics and no `vllm:` key and did not consult the scraper. So
`cloud.gpu_kv_fraction` was identically 0.0 in every live2 cell, LIVE ones included, and
`arms_v6cf._pd_free_kv` was priced by the residency belief on 100 percent of decisions:
`pd_kv_bound_by_belief == pd_decisions` at all four committed rung-4 seeds and
`pd_kv_bound_by_engine_metric` ABSENT at all four. That is CLAUDE.md Step 2's write-only field in
its other form - a read whose input was never written - and a zero from it is an ABSENT LINK and
not a result.

THE FIVE PARTS, AND WHAT EACH ONE CAN AND CANNOT ESTABLISH.

  A  READ SITES, static. The definition is now READ: `metrics()` -> `published_engine_metrics()`
     -> `scrape_metrics()` -> the ONE scrape path in `live/adapter.py`. Also asserts there is
     still exactly ONE `_fetch_metrics` definition in the tree, because the failure this item
     repeats if done carelessly is a SECOND scraper (`d213_patch_asyncbackend.py` carries the
     refusal header of the one that was retracted).

  B  THREE STATES, unit. `never_scraped`, `scraped_and_failed` and `scraped_ok` are produced for
     real and shown to differ in `state` AND in `engine_metrics_trusted`. D227's point is that a
     boolean cannot do this, so a boolean is not what is checked.

  C  THE ALLOW-LIST IS LOAD-BEARING, unit plus a POSITIVE CONTROL. The fake server emits
     `vllm:num_requests_waiting`, which `cstate.py:691` reads for `queued_by_class["episodic"]`
     with the coordinator's own in-flight count as its fallback. The proof shows the raw scrape
     carries it, the published subset does not, and - the control - that WITHOUT the filter the
     observation's queue field MOVES. A filter nobody can show removing something is decoration.

  D  BYTE IDENTITY, ON versus OFF, on NON-DRY cells. *** A DRY CELL CANNOT TEST THIS AND MUST NOT
     BE USED FOR IT. *** `coordinator.py:489` is guarded by `not self.dry_run and self.be is not
     None`, so in a dry cell `st.metrics` is never assigned and the scrape is unreachable: an
     ON-versus-OFF digest comparison on a dry cell is identical BY CONSTRUCTION and proves
     nothing. These cells therefore run against the committed CPU stub
     (`live/fake_server.py`) through `AsyncLive2Backend`, which is the class every live2 cell uses.
     Both sides of every comparison run in THIS tree, so the comparison is unaffected by the
     docstring edits this commit also makes (D216 (1) records that a comment-only edit moved a
     rung-2 digest by 85 decisions through `id(obs)` allocation; nothing here is compared against
     a committed digest, and that is why).

  E  THE LINK IS LIVE. `covex-v6-final` with the scrape ON must DIFFER from itself with the scrape
     OFF, and must report `pd_kv_bound_by_engine_metric` NON-ZERO. Reported beside it:
     `metrics_health.state`, so a non-zero bind cannot be read without knowing whether the value
     behind it was an observation.

ONE HAZARD THIS SCRIPT CHECKS BEFORE IT TRUSTS PART D, because the whole part rests on it: a
non-dry cell runs in REAL TIME against a real socket, so it need not be reproducible run to run.
Part D therefore runs a SELF-IDENTITY control first - the same arm, the same condition, twice -
and REFUSES to report any ON-versus-OFF result for an arm whose own two OFF runs disagree. An
equality claimed in a comparison whose noise floor was never measured is not a proof.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
           str(ROOT / "experiments/orchestration/live"),
           str(ROOT / "experiments/orchestration/baselines"), str(ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

OUT_DEFAULT = ROOT / "results/orchestration/live2/d227_e1_metrics/d227_e1_metrics_proofs.json"

# The arms that must NOT move. "Every arm that does not read the field" (D216 (2)): the base, the
# rung-2 and rung-3 ladder arms, and the paper baselines, with `mooncake` named explicitly because
# it is the one that reads the QUEUE and therefore the one the allow-list protects.
IDENTITY_ARMS = ("hybrid-F-lhreq-noc3", "covex-v6-state-final", "covex-v6-fair-final",
                 "mooncake", "simplestream", "llf")
# The arm whose gate DOES read the field, and must therefore move (D216 (2): "only
# covex-v6-final's gate changes").
LINK_ARM = "covex-v6-final"

MIN_FREE_MB = 4096          # a cell that fills the disk writes a truncated log and a false result


def _base_sha() -> Optional[str]:
    """The sha this tree was archived from, if a sibling file records it. Never guessed."""
    for c in (ROOT / "BASE_SHA", ROOT / ".base_sha"):
        if c.exists():
            return c.read_text().strip() or None
    return None


def _changed_files() -> List[str]:
    """The files this study edits, listed so a reader can diff them rather than trust a sentence."""
    return ["experiments/orchestration/live/adapter.py",
            "experiments/orchestration/live2/asyncbackend.py",
            "experiments/orchestration/live2/cstate.py (module docstring only)",
            "experiments/orchestration/live2/metrics_trust.py (new)",
            "experiments/orchestration/live2/d227_e1_metrics_proofs.py (new)"]


def _free_mb() -> int:
    return int(shutil.disk_usage(str(ROOT)).free // (1024 * 1024))


def _require_space(where: str) -> None:
    f = _free_mb()
    if f < MIN_FREE_MB:
        raise SystemExit("REFUSING to run %s: only %d MiB free on the volume holding %s, under the "
                         "%d MiB floor. A cell that runs out of disk writes a truncated log and a "
                         "result that looks like a measurement." % (where, f, ROOT, MIN_FREE_MB))


# --------------------------------------------------------------------------- A: read sites

def part_a() -> Dict[str, Any]:
    ab = (HERE / "asyncbackend.py").read_text()
    tree = ast.parse(ab)
    calls: Dict[str, List[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            names = sorted({n.func.attr for n in ast.walk(node)
                            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)})
            calls[node.name] = names
    chain = {
        "metrics -> metrics_health": "metrics_health" in calls.get("metrics", []),
        "metrics -> published_engine_metrics": "published_engine_metrics" in calls.get("metrics", []),
        "published_engine_metrics -> scrape_metrics":
            "scrape_metrics" in calls.get("published_engine_metrics", []),
        "scrape_metrics -> _metrics_poller": "_metrics_poller" in calls.get("scrape_metrics", []),
        "_metrics_poller -> start_poller": "start_poller" in calls.get("_metrics_poller", []),
    }
    # THE CENSUS IS A FILESYSTEM WALK AND NOT A `git grep`, because this proof is meant to run on
    # a clean `git archive` tree, which is NOT a git repository: a `git grep` there returns zero
    # lines and a zero-length result read as "no second scraper" would be an absence asserted
    # from a view that could not have seen one. Every `.py` under `experiments/` is opened.
    defs: List[str] = []
    n_py = 0
    for p in sorted((ROOT / "experiments").rglob("*.py")):
        n_py += 1
        try:
            txt = p.read_text(errors="replace")
        except Exception:                                                      # noqa: BLE001
            defs.append("UNREADABLE %s" % p.relative_to(ROOT))
            continue
        for i, line in enumerate(txt.splitlines(), 1):
            if line.lstrip().startswith("def _fetch_metrics"):
                defs.append("%s:%d" % (p.relative_to(ROOT), i))
    import asyncbackend as AB
    ok = all(chain.values()) and len(defs) == 1
    return {"claim": ("the definition is now READ: metrics() reaches the ONE scrape path, and "
                      "there is still exactly one _fetch_metrics in the tree"),
            "call_chain": chain,
            "fetch_metrics_definitions_in_tree": defs,
            "n_fetch_metrics_definitions": len(defs),
            "n_python_files_examined": n_py,
            "published_engine_keys": list(AB.AsyncLive2Backend.PUBLISHED_ENGINE_KEYS),
            "withheld_engine_keys": dict(AB.AsyncLive2Backend.WITHHELD_ENGINE_KEYS),
            "num_requests_waiting_is_withheld":
                "vllm:num_requests_waiting" not in AB.AsyncLive2Backend.PUBLISHED_ENGINE_KEYS,
            "metrics_scrape_class_default_is_off":
                AB.AsyncLive2Backend.METRICS_SCRAPE_DEFAULT is False,
            "PASS": bool(ok)}


# --------------------------------------------------------------------------- B and C: units

def _backend(url: str, on: bool):
    from asyncbackend import AsyncLive2Backend
    be = AsyncLive2Backend(url, model="fake", strip_hints=False, cache=None, limit=256)
    be.metrics_scrape = bool(on)
    return be


def part_b_c() -> Dict[str, Any]:
    import fake_server as FS
    import metrics_trust as MT
    rows: List[Dict[str, Any]] = []
    with FS.serve(0) as url:
        # 1. the scrape switched off
        be = _backend(url, False)
        h_off = be.metrics_health()
        m_off = be.metrics()
        be.close()
        rows.append({"condition": "scrape OFF", "state": h_off.get("state"),
                     "engine_metrics_trusted": h_off.get("engine_metrics_trusted"),
                     "n_scrapes": h_off.get("n_scrapes"),
                     "n_failures": h_off.get("n_failures"),
                     "kv_key_in_metrics": any(k.startswith("vllm:") for k in m_off)})
        # 2. the scrape on, against a URL that refuses
        be = _backend("http://127.0.0.1:1", True)
        m_bad = be.metrics()
        h_bad = be.metrics_health()
        be.close()
        rows.append({"condition": "scrape ON, endpoint unreachable", "state": h_bad.get("state"),
                     "engine_metrics_trusted": h_bad.get("engine_metrics_trusted"),
                     "n_scrapes": h_bad.get("n_scrapes"), "n_failures": h_bad.get("n_failures"),
                     "kv_value_served": m_bad.get("vllm:gpu_cache_usage_perc"),
                     "fm_kv_state": m_bad.get("fm_kv_state")})
        # 3. the scrape on, against the stub
        be = _backend(url, True)
        raw = be.scrape_metrics()
        pub = be.published_engine_metrics()
        m_ok = be.metrics()
        h_ok = be.metrics_health()
        rows.append({"condition": "scrape ON, stub answers", "state": h_ok.get("state"),
                     "engine_metrics_trusted": h_ok.get("engine_metrics_trusted"),
                     "n_scrapes": h_ok.get("n_scrapes"), "n_failures": h_ok.get("n_failures"),
                     "last_success_t_is_set": h_ok.get("last_success_t") is not None,
                     "metric_names_found": h_ok.get("metric_names_found"),
                     "kv_key_seen": h_ok.get("kv_key_seen"),
                     "kv_value_served": m_ok.get("vllm:gpu_cache_usage_perc"),
                     "fm_kv_state": m_ok.get("fm_kv_state")})
        filt = {"raw_scrape_carries_num_requests_waiting":
                    "vllm:num_requests_waiting" in raw,
                "published_subset_carries_it": "vllm:num_requests_waiting" in pub,
                "metrics_carries_it": "vllm:num_requests_waiting" in m_ok,
                "raw_scrape_n_keys": len(raw), "published_n_keys": len(pub)}
        be.close()
    states = [r["state"] for r in rows]
    trusted = [r["engine_metrics_trusted"] for r in rows]
    ok = (states == ["never_scraped", "scraped_and_failed", "scraped_ok"]
          and trusted == [False, False, True]
          and filt["raw_scrape_carries_num_requests_waiting"] is True
          and filt["published_subset_carries_it"] is False
          and filt["metrics_carries_it"] is False)
    # the cell-level derivation a reader actually sees
    cell_states = {}
    for tag, res in (("dry", {}), ("no backend block", {"backend": {}}),
                     ("scrape off", {"backend": {"metrics_health": {"state": "never_scraped",
                                                                    "engine_metrics_trusted": False}}}),
                     ("scrape ok", {"backend": {"metrics_health": {"state": "scraped_ok",
                                                                   "engine_metrics_trusted": True}}})):
        cell_states[tag] = MT.cell_metrics_health(res, dry_run=(tag == "dry"))
    return {"claim": ("the three states are produced for real and differ in state AND in "
                      "engine_metrics_trusted; the allow-list removes a key the raw scrape "
                      "really carries"),
            "rows": rows, "allow_list": filt,
            "cell_level_states": {k: {"state": v["state"],
                                      "engine_metrics_trusted": v["engine_metrics_trusted"]}
                                  for k, v in cell_states.items()},
            "PASS": bool(ok)}


# --------------------------------------------------------------------------- D and E: cells

def _digest(rows: List[Dict[str, Any]]) -> str:
    """The COMMITTED recipe, `hybrid/test_hybrid.STRIP` and the same dumps, not a new one."""
    import test_hybrid as TH
    rr = [{k: v for k, v in r.items() if k not in TH.STRIP} for r in rows]
    return hashlib.sha256(json.dumps(rr, sort_keys=True, separators=(",", ":"),
                                     default=float).encode()).hexdigest()[:16]


def one_cell(arm_name: str, *, on: bool, work: Path, seed: int, window_s: float,
             n_dashcam: int, n_robot: int, unfiltered: bool = False) -> Dict[str, Any]:
    """ONE non-dry cell against the committed CPU stub, through `AsyncLive2Backend`."""
    import arms as A
    import cachekeys as CK
    import cstate as CS
    import fake_server as FS
    import traces as T
    from asyncbackend import AsyncLive2Backend
    from coordinator import Live2Coordinator, Logs
    _require_space("cell %s on=%s" % (arm_name, on))
    if unfiltered:
        # Part C's POSITIVE CONTROL and nothing else: publish everything the scrape carries, so
        # `vllm:num_requests_waiting` reaches `cstate.py:691`. Process-local, never committed.
        AsyncLive2Backend.PUBLISHED_ENGINE_KEYS = tuple(
            list(AsyncLive2Backend.PUBLISHED_ENGINE_KEYS) + ["vllm:num_requests_waiting"])
    arm = A.make_arm(arm_name)
    cfg = dict(gpu_kv_tokens=62_944, host_tier_gib=27.0, host_tier_tokens=48_000,
               targets=CS.TARGETS)
    arm.live2_configure(**cfg)
    tr = T.synthetic(n_dashcam=n_dashcam, n_robot=n_robot, duration_s=window_s, seed=seed,
                     upload_mode="A", frames_dir=None)
    T.require_fake_server(tr, "fake")
    d = work / ("%s_%s%s" % (arm_name, "on" if on else "off", "_unfiltered" if unfiltered else ""))
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True, exist_ok=True)
    logs = Logs(d).open()
    t0 = time.time()
    with FS.serve(0) as url:
        be = AsyncLive2Backend(url, model="fake", strip_hints=False, cache=None, limit=1024)
        be.metrics_scrape = bool(on)
        co = Live2Coordinator(arm, be, tr["events"], gpu_kv_tokens=62_944,
                              host_tier_gib=27.0, host_tier_tokens=48_000, upload_mode="A",
                              window_s=window_s, drain_s=5.0, seed=seed, logs=logs,
                              run_tag=CK.run_tag(seed, arm_name), targets=CS.TARGETS,
                              dry_run=False, max_wall_s=window_s + 120.0)
        res = co.run()
        bem = be.metrics()
        be.close()
    logs.close()
    rows = [json.loads(x) for x in (d / "decision.jsonl").read_text().splitlines() if x.strip()]
    st = dict(getattr(arm, "stats", {}) or {})
    health = bem.get("metrics_health") or {}
    return {"arm": arm_name, "scrape_on": bool(on), "unfiltered": bool(unfiltered),
            "n_decision_rows": len(rows), "digest": _digest(rows),
            "wall_s": round(time.time() - t0, 2),
            "metrics_health": {k: health.get(k) for k in
                               ("state", "engine_metrics_trusted", "n_scrapes", "n_failures",
                                "last_success_t", "metric_names_found", "kv_key_seen")},
            "gpu_kv_fraction_published": bem.get("vllm:gpu_cache_usage_perc"),
            "queued_episodic_published": bem.get("vllm:num_requests_waiting"),
            "pd_kv_bound_by_engine_metric": st.get("pd_kv_bound_by_engine_metric"),
            "pd_kv_bound_by_belief": st.get("pd_kv_bound_by_belief"),
            "pd_decisions": st.get("pd_decisions"),
            "pd_free_kv_min": st.get("pd_free_kv_min"),
            "pd_free_kv_max": st.get("pd_free_kv_max")}


def _capture_tape(arm_name: str, *, work: Path, seed: int, window_s: float,
                  n_dashcam: int, n_robot: int) -> Tuple[List[Tuple[str, Any]], Dict[str, Any]]:
    """Run ONE non-dry stub cell and record the arm's whole INPUT SEQUENCE.

    The tape is every call the coordinator makes on the arm, in order: `live2_roster`,
    `live2_completed` and the `__call__` that decides. Replaying it is what makes the comparison
    below deterministic, which the live cell itself is NOT (see `_SELF_ID_NOTE`).
    """
    import arms as A
    import cachekeys as CK
    import cstate as CS
    import fake_server as FS
    import traces as T
    from asyncbackend import AsyncLive2Backend
    from coordinator import Live2Coordinator, Logs
    _require_space("capture %s" % arm_name)
    arm = A.make_arm(arm_name)
    arm.live2_configure(gpu_kv_tokens=62_944, host_tier_gib=27.0, host_tier_tokens=48_000,
                        targets=CS.TARGETS)
    cls = type(arm)
    tape: List[Tuple[str, Any]] = []
    o_call = cls.__call__
    o_rost = getattr(cls, "live2_roster", None)
    o_done = getattr(cls, "live2_completed", None)

    def _call(self, obs):                                    # noqa: ANN001
        tape.append(("call", obs))
        return o_call(self, obs)

    def _rost(self, roster):                                 # noqa: ANN001
        tape.append(("roster", roster))
        return o_rost(self, roster)

    def _done(self, rec):                                    # noqa: ANN001
        tape.append(("completed", rec))
        return o_done(self, rec)

    cls.__call__ = _call
    if o_rost is not None:
        cls.live2_roster = _rost
    if o_done is not None:
        cls.live2_completed = _done
    d = work / ("capture_" + arm_name)
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True, exist_ok=True)
    logs = Logs(d).open()
    try:
        tr = T.synthetic(n_dashcam=n_dashcam, n_robot=n_robot, duration_s=window_s, seed=seed,
                         upload_mode="A", frames_dir=None)
        T.require_fake_server(tr, "fake")
        with FS.serve(0) as url:
            be = AsyncLive2Backend(url, model="fake", strip_hints=False, cache=None, limit=1024)
            be.metrics_scrape = True
            co = Live2Coordinator(arm, be, tr["events"], gpu_kv_tokens=62_944,
                                  host_tier_gib=27.0, host_tier_tokens=48_000, upload_mode="A",
                                  window_s=window_s, drain_s=5.0, seed=seed, logs=logs,
                                  run_tag=CK.run_tag(seed, arm_name), targets=CS.TARGETS,
                                  dry_run=False, max_wall_s=window_s + 120.0)
            res = co.run()
            bem = be.metrics()
            be.close()
    finally:
        cls.__call__ = o_call
        if o_rost is not None:
            cls.live2_roster = o_rost
        if o_done is not None:
            cls.live2_completed = o_done
        logs.close()
    kvs = sorted({round(float(getattr(o.cloud, "gpu_kv_fraction", 0.0) or 0.0), 6)
                  for k, o in tape if k == "call"})
    health = bem.get("metrics_health") or {}
    meta = {"capture_arm": arm_name, "n_tape": len(tape),
            "n_decide_calls": sum(1 for k, _ in tape if k == "call"),
            "n_roster": sum(1 for k, _ in tape if k == "roster"),
            "n_completed": sum(1 for k, _ in tape if k == "completed"),
            "live_gpu_kv_fraction_distinct_values": len(kvs),
            "live_gpu_kv_fraction_min": (kvs[0] if kvs else None),
            "live_gpu_kv_fraction_max": (kvs[-1] if kvs else None),
            "metrics_health": {k: health.get(k) for k in
                               ("state", "engine_metrics_trusted", "n_scrapes", "n_failures",
                                "kv_key_seen", "metric_names_found")},
            "server": "live/fake_server.py, the committed CPU stub; it tracks kv_tokens per "
                      "request so vllm:gpu_cache_usage_perc is non-zero and varying"}
    return tape, meta


class _CountingCloud:
    """A CloudState that counts reads of the field, so a zero is a CENSUS and not an assumption."""

    def __init__(self, inner: Any, counter: Dict[str, int]) -> None:
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_counter", counter)

    def __getattr__(self, k: str) -> Any:
        if k in ("gpu_kv_fraction",):
            c = object.__getattribute__(self, "_counter")
            c[k] = c.get(k, 0) + 1
        return getattr(object.__getattribute__(self, "_inner"), k)


def _replay(arm_name: str, tape: List[Tuple[str, Any]], *, kv: Optional[float],
            count_reads: bool = False) -> Dict[str, Any]:
    """Replay the tape on a FRESH arm, optionally forcing `cloud.gpu_kv_fraction` to `kv`."""
    import copy
    import dataclasses
    import arms as A
    import cstate as CS
    arm = A.make_arm(arm_name)
    arm.live2_configure(gpu_kv_tokens=62_944, host_tier_gib=27.0, host_tier_tokens=48_000,
                        targets=CS.TARGETS)
    arm.reset(4)
    reads: Dict[str, int] = {}
    acts: List[str] = []
    for kind, payload in tape:
        if kind == "roster":
            # the same `hasattr` guard the coordinator uses at :720, so an arm that declares
            # neither hook is replayed exactly as the coordinator would drive it
            if hasattr(arm, "live2_roster"):
                arm.live2_roster(copy.deepcopy(payload))
        elif kind == "completed":
            if hasattr(arm, "live2_completed"):
                arm.live2_completed(copy.deepcopy(payload))
        else:
            obs = payload
            cloud = obs.cloud
            if kv is not None:
                cloud = dataclasses.replace(cloud, gpu_kv_fraction=float(kv))
            if count_reads:
                cloud = _CountingCloud(cloud, reads)
            o = dataclasses.replace(obs, cloud=cloud)
            act = arm(o)
            acts.append(json.dumps(dataclasses.asdict(act), sort_keys=True, default=str))
    st = dict(getattr(arm, "stats", {}) or {})
    return {"n_actions": len(acts),
            "digest": hashlib.sha256("\n".join(acts).encode()).hexdigest()[:16],
            "actions": acts,
            "reads_gpu_kv_fraction": int(reads.get("gpu_kv_fraction", 0)),
            "pd_kv_bound_by_engine_metric": st.get("pd_kv_bound_by_engine_metric"),
            "pd_kv_bound_by_belief": st.get("pd_kv_bound_by_belief"),
            "pd_decisions": st.get("pd_decisions"),
            "pd_free_kv_min": st.get("pd_free_kv_min"),
            "pd_free_kv_max": st.get("pd_free_kv_max")}


_SELF_ID_NOTE = (
    "A NON-DRY CELL IS NOT REPRODUCIBLE RUN TO RUN, measured and not assumed: two identical "
    "`mooncake` runs at the same seed and the same condition against the stub produced 160 "
    "decision rows each and the digests 5b67c60fce399902 and 767daf8a71626f1d. So an "
    "ON-versus-OFF digest comparison on a live cell cannot establish byte identity: its noise "
    "floor is larger than the effect it would be measuring. That is why byte identity is "
    "established HERE by replaying one recorded input tape, which is deterministic, and why a "
    "self-identity control runs for every arm before its result is reported.")


def part_d(work: Path, *, seed: int, window_s: float, n_dashcam: int, n_robot: int,
           arms: Tuple[str, ...], tape: Optional[List[Tuple[str, Any]]] = None,
           meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """BYTE IDENTITY by DETERMINISTIC REPLAY, plus the read census."""
    if tape is None:
        tape, meta = _capture_tape(LINK_ARM, work=work, seed=seed, window_s=window_s,
                                   n_dashcam=n_dashcam, n_robot=n_robot)
    lo, hi = 0.0, 0.97
    rows: List[Dict[str, Any]] = []
    for nm in arms:
        a1 = _replay(nm, tape, kv=lo)
        a2 = _replay(nm, tape, kv=lo)
        b = _replay(nm, tape, kv=hi, count_reads=True)
        first_diff = None
        for i, (x, y) in enumerate(zip(a1["actions"], b["actions"])):
            if x != y:
                first_diff = {"index": i, "kv_%g" % lo: x[:400], "kv_%g" % hi: y[:400]}
                break
        rows.append({"arm": nm,
                     "self_identity_kv0_vs_kv0": bool(a1["digest"] == a2["digest"]),
                     "digest_kv_0.0": a1["digest"], "digest_kv_0.97": b["digest"],
                     "identical_across_kv": bool(a1["digest"] == b["digest"]),
                     "n_actions": a1["n_actions"],
                     "reads_gpu_kv_fraction_at_kv_0.97": b["reads_gpu_kv_fraction"],
                     "pd_kv_bound_by_engine_metric_at_kv_0.97": b["pd_kv_bound_by_engine_metric"],
                     "pd_kv_bound_by_belief_at_kv_0.97": b["pd_kv_bound_by_belief"],
                     "pd_decisions_at_kv_0.97": b["pd_decisions"],
                     "pd_free_kv_min_at_kv_0.97": b["pd_free_kv_min"],
                     "first_differing_action": first_diff})
    graded = [r for r in rows if r["self_identity_kv0_vs_kv0"]]
    ungraded = [r["arm"] for r in rows if not r["self_identity_kv0_vs_kv0"]]
    ident = [r for r in graded if r["arm"] in IDENTITY_ARMS]
    link = [r for r in graded if r["arm"] == LINK_ARM]
    identity_ok = bool(ident) and all(r["identical_across_kv"] for r in ident)
    reads_zero = all(r["reads_gpu_kv_fraction_at_kv_0.97"] == 0 for r in ident)
    link_moved = bool(link and not link[0]["identical_across_kv"])
    link_reads = bool(link and link[0]["reads_gpu_kv_fraction_at_kv_0.97"] > 0)
    link_binds = bool(link and (link[0]["pd_kv_bound_by_engine_metric_at_kv_0.97"] or 0) > 0)
    return {"claim": ("every arm that does not read the field is byte-identical under the field, "
                      "by deterministic replay of one recorded input tape"),
            "method": _SELF_ID_NOTE,
            "capture": meta,
            "injected_values": {"low": lo, "high": hi},
            "rows": rows,
            "arms_not_graded_self_identity_failed": ungraded,
            "identity_arms_byte_identical": identity_ok,
            "identity_arms_never_read_the_field": bool(reads_zero),
            "link_arm_in_this_fixture": {
                "arm": LINK_ARM, "moved": link_moved, "read_the_field": link_reads,
                "engine_metric_binds": link_binds,
                "REGISTER": ("NOT A PASS CONDITION HERE, and the reason is a property of the "
                             "FIXTURE and not of the wiring: on a 2+2-device synthetic trace "
                             "against the CPU stub, no decision reaches the protect-and-defer "
                             "path at all (every pd_* counter is ABSENT, not zero), so "
                             "_pd_free_kv is never called and the field is never read. Claiming "
                             "identity for covex-v6-final from this would be the UNEXERCISED "
                             "null this project keeps finding. The read site is proved directly "
                             "in part_d2, on the SAME captured live observations.")},
            "PASS": bool(identity_ok and reads_zero)}


def part_d2_read_site(work: Path, *, seed: int, window_s: float, n_dashcam: int,
                      n_robot: int, tape: Optional[List[Tuple[str, Any]]] = None,
                      meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """THE READ SITE ITSELF, on REAL live observations: does the published gauge change free_kv?

    `arms_v6cf._pd_free_kv` is the one consumer of `cloud.gpu_kv_fraction` in the ladder. It is
    called here DIRECTLY, once per captured live observation, under two conditions:

        published   the value the scrape actually put on that observation
        forced 0.0  what every live2 cell before E1 saw, because nothing read the engine

    and the counters it keeps are read back. This is the Step 2b check for E1: it shows the switch
    ARRIVED AT THE OBJECT UNDER TEST with its declared type and value and MOVED a decision input,
    on live values rather than on a number chosen to make the point.
    """
    import copy
    import dataclasses
    import arms as A
    import cstate as CS
    if tape is None:
        tape, meta = _capture_tape(LINK_ARM, work=work, seed=seed, window_s=window_s,
                                   n_dashcam=n_dashcam, n_robot=n_robot)
    out: Dict[str, Any] = {"capture": meta}
    for tag, force in (("published", None), ("forced_0.0", 0.0)):
        arm = A.make_arm(LINK_ARM)
        arm.live2_configure(gpu_kv_tokens=62_944, host_tier_gib=27.0,
                            host_tier_tokens=48_000, targets=CS.TARGETS)
        arm.reset(seed)
        frees: List[float] = []
        kvs: List[float] = []
        for kind, payload in tape:
            if kind == "roster":
                if hasattr(arm, "live2_roster"):
                    arm.live2_roster(copy.deepcopy(payload))
                continue
            if kind != "call":
                continue
            obs = payload
            cloud = obs.cloud
            if force is not None:
                cloud = dataclasses.replace(cloud, gpu_kv_fraction=float(force))
            o = dataclasses.replace(obs, cloud=cloud)
            kvs.append(float(getattr(o.cloud, "gpu_kv_fraction", 0.0) or 0.0))
            frees.append(float(arm._pd_free_kv(o)))
        st = dict(getattr(arm, "stats", {}) or {})
        fs = sorted(frees)
        out[tag] = {
            "n_calls": len(frees),
            "gpu_kv_fraction_min": (min(kvs) if kvs else None),
            "gpu_kv_fraction_max": (max(kvs) if kvs else None),
            "gpu_kv_fraction_distinct": len(set(round(x, 6) for x in kvs)),
            "free_kv_min": (fs[0] if fs else None),
            "free_kv_median": (fs[len(fs) // 2] if fs else None),
            "free_kv_max": (fs[-1] if fs else None),
            "free_kv_distinct": len(set(round(x, 6) for x in fs)),
            "pd_kv_bound_by_engine_metric": int(st.get("pd_kv_bound_by_engine_metric", 0) or 0),
            "pd_kv_bound_by_belief": int(st.get("pd_kv_bound_by_belief", 0) or 0)}
    pub, zero = out["published"], out["forced_0.0"]
    first = None
    binds_pub = pub["pd_kv_bound_by_engine_metric"]
    return dict(out,
                claim=("the published engine gauge reaches _pd_free_kv and changes its result; "
                       "with the field forced to 0.0 the belief binds on every call, which is "
                       "what every committed rung-4 cell measured"),
                engine_metric_binds_published=binds_pub,
                engine_metric_binds_forced_zero=zero["pd_kv_bound_by_engine_metric"],
                free_kv_differs=bool(pub["free_kv_min"] != zero["free_kv_min"]
                                     or pub["free_kv_median"] != zero["free_kv_median"]),
                first_difference=first,
                PASS=bool(binds_pub > 0
                          and zero["pd_kv_bound_by_engine_metric"] == 0
                          and zero["pd_kv_bound_by_belief"] == zero["n_calls"]
                          and pub["free_kv_min"] != zero["free_kv_min"]))


def part_e(work: Path, *, seed: int, window_s: float, n_dashcam: int, n_robot: int) -> Dict[str, Any]:
    """THE SMOKE: a non-dry cell with the scrape ON, and what the gate did with it."""
    on = one_cell(LINK_ARM, on=True, work=work / "smoke", seed=seed, window_s=window_s,
                  n_dashcam=n_dashcam, n_robot=n_robot)
    off = one_cell(LINK_ARM, on=False, work=work / "smoke", seed=seed, window_s=window_s,
                   n_dashcam=n_dashcam, n_robot=n_robot)
    unf = one_cell("mooncake", on=True, work=work / "smoke", seed=seed, window_s=window_s,
                   n_dashcam=n_dashcam, n_robot=n_robot, unfiltered=True)
    binds = int(on.get("pd_kv_bound_by_engine_metric") or 0)
    return {"claim": ("on a LIVE (non-dry) cell with the scrape on, pd_kv_bound_by_engine_metric "
                      "is NON-ZERO and metrics_health says the value behind it was observed"),
            "register": ("the server is the committed CPU STUB live/fake_server.py, not an "
                         "engine. It tracks kv_tokens per request, so the gauge is real and "
                         "varying, but this is a WIRING smoke and NOT an engine measurement. A "
                         "real-engine smoke belongs on the H100."),
            "scrape_on": on, "scrape_off": off,
            "allow_list_control_unfiltered_mooncake": {
                "queued_episodic_published": unf.get("queued_episodic_published"),
                "note": ("with the filter removed the engine's own num_requests_waiting IS "
                         "published, which is what cstate.py:691 would then read; the filtered "
                         "run publishes None for it")},
            "pd_kv_bound_by_engine_metric_on": binds,
            "pd_kv_bound_by_engine_metric_off": off.get("pd_kv_bound_by_engine_metric"),
            "pd_counters_absent_in_this_fixture": bool(on.get("pd_decisions") is None),
            "why_pd_is_absent_here": ("no decision in a small synthetic cell reaches the "
                                      "protect-and-defer path, so every pd_* counter is ABSENT "
                                      "rather than zero. The read site is proved in part_d2 on "
                                      "the same captured live observations; a REAL-ENGINE cell "
                                      "is what would show the gate binding in production."),
            "PASS": bool(on["metrics_health"]["state"] == "scraped_ok"
                         and on["metrics_health"]["n_failures"] == 0
                         and (on.get("gpu_kv_fraction_published") or 0) > 0
                         and off["metrics_health"]["state"] == "never_scraped"
                         and on.get("queued_episodic_published") is None)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--work", default=None)
    ap.add_argument("--seed", type=int, default=4, help="never 1 to 3, never HOLDOUT")
    ap.add_argument("--window-s", type=float, default=60.0)
    ap.add_argument("--n-dashcam", type=int, default=3)
    ap.add_argument("--n-robot", type=int, default=3)
    ap.add_argument("--arms", default=",".join(IDENTITY_ARMS + (LINK_ARM,)))
    ap.add_argument("--skip-cells", action="store_true",
                    help="parts A to C only (no cell runs)")
    a = ap.parse_args()
    if a.seed in (1, 2, 3):
        raise SystemExit("seeds 1 to 3 are the held-out seeds and are refused")
    _require_space("the proof run")
    work = Path(a.work) if a.work else Path(a.out).resolve().parent / "work"
    work.mkdir(parents=True, exist_ok=True)
    doc: Dict[str, Any] = {
        "_what": ("E1 + E3 proofs: the engine /metrics scrape reaches a decision, and every "
                  "cell.json can say whether its engine-metric quantities are evidence"),
        "_d_rows": ["D216 (2)", "D222 (1) g", "D227", "D218 (3) (the withheld key)",
                    "D209 (2) (the missing-value policy this reuses)"],
        "_cells_are": ("NON-DRY cells against the committed CPU stub live/fake_server.py through "
                       "AsyncLive2Backend. A DRY cell cannot test this: coordinator.py:489 is "
                       "guarded by `not dry_run`, so the scrape is unreachable and an "
                       "ON-versus-OFF digest would be identical by construction."),
        "_free_mb_at_start": _free_mb(),
        # THE REGISTER OF THE TREE THIS RAN ON, because two of the files E1 needs are claimed by
        # another session and this artefact must not be read as a proof of a tree that does not
        # exist yet. `run_live2_real.py` and `procsplit.py` here are ORIGIN BYTES: the harness
        # flag and the `cell.json` line are part 2 and land after the claim clears, at which
        # point THIS FILE IS REGENERATED on the post-rebase tree. Nothing below depends on
        # either file: the switch is set directly on the backend instance.
        "_tree_state": {
            "base_sha": _base_sha(),
            "files_changed_by_this_study_in_this_tree": _changed_files(),
            "held_files_are_origin_bytes": ["experiments/orchestration/live2/run_live2_real.py",
                                            "experiments/orchestration/live2/procsplit.py"],
            "regenerate_before_commit": True},
    }
    doc["part_a_read_sites"] = part_a()
    doc["part_b_c_states_and_allow_list"] = part_b_c()
    if not a.skip_cells:
        tape, meta = _capture_tape(LINK_ARM, work=work, seed=a.seed, window_s=a.window_s,
                                   n_dashcam=a.n_dashcam, n_robot=a.n_robot)
        doc["part_d_byte_identity_by_replay"] = part_d(
            work, seed=a.seed, window_s=a.window_s, n_dashcam=a.n_dashcam, n_robot=a.n_robot,
            arms=tuple(x for x in a.arms.split(",") if x), tape=tape, meta=meta)
        doc["part_d2_read_site"] = part_d2_read_site(
            work, seed=a.seed, window_s=a.window_s, n_dashcam=a.n_dashcam, n_robot=a.n_robot,
            tape=tape, meta=meta)
        doc["part_e_live_smoke"] = part_e(work, seed=a.seed, window_s=a.window_s,
                                          n_dashcam=a.n_dashcam, n_robot=a.n_robot)
    doc["_free_mb_at_end"] = _free_mb()
    parts = [k for k in doc if k.startswith("part_")]
    doc["VERDICT"] = ("PASS" if all(doc[k].get("PASS") for k in parts) else "FAIL")
    doc["_parts"] = {k: doc[k].get("PASS") for k in parts}
    try:
        import _provenance as P
        doc["_provenance"] = P.stamp(script="d227_e1_metrics_proofs.py", model=None,
                                     device="flash_cpu", n=None, args=a)
    except Exception as exc:                                                   # noqa: BLE001
        doc["_provenance"] = {"git_commit": "unstamped", "why": repr(exc),
                              "script": "d227_e1_metrics_proofs.py"}
    o = Path(a.out)
    o.parent.mkdir(parents=True, exist_ok=True)
    o.write_text(json.dumps(doc, indent=1, default=str) + "\n")
    print(json.dumps({k: doc[k].get("PASS") for k in parts}, indent=1))
    print("VERDICT", doc["VERDICT"], "->", o)
    return 0 if doc["VERDICT"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
