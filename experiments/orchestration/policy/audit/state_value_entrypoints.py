#!/usr/bin/env python3
"""Settle F-A2: which `state_value` entry point is authoritative, over ONE candidate population.

Three numbers have been reported for "the state value" and they disagree:

  session 2 (F-A2)  the BETWEEN-BRANCH DIFFERENCE is exactly zero in 124,354 of 124,354
                    candidates, with F2 on AND off
  session 1 (first) `_state_value` returns 0.009216 on every one of 1,365 calls, and F2 zeroes
                    the SUM: 28.1 percent zero with F2 off against 100 percent with it on
  session 1 (new)   `state_value` returns zero in 100 percent of calls in BOTH F2 conditions

They are not three readings of one quantity. `state_value` is a CACHING WRAPPER around
`_state_value` and shadow mode asserts the two agree, so they cannot differ in value. What differ
are the CALL SITES and the quantity being summarised:

  rollout.py:701      `from .readiness import ... state_value` INSIDE the function, so the name is
                      resolved at call time and a patch on `readiness` DOES take effect
  coordinator.py:21   `from .readiness import state_value` at MODULE level, so the name is bound
                      at import time and a patch on `readiness` does NOT take effect

So patching one module catches one call site and silently misses the other. This script patches
`readiness._state_value` (which every path reaches on a cache miss) AND both module bindings of
`state_value`, attributes every computation to its call site by frame, and reports the per-call
value, the per-branch sum and the between-branch difference side by side in both F2 conditions.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402


def _callsite() -> str:
    """Attribute a computation to the call site that asked for it."""
    f = sys._getframe(1)
    seen = []
    while f is not None:
        name = f.f_code.co_filename.rsplit("/", 1)[-1]
        if name in ("rollout.py", "coordinator.py", "planner_rc.py"):
            seen.append("%s:%s" % (name, f.f_code.co_name))
        f = f.f_back
    return seen[0] if seen else "unattributed"


def probe(switches: Dict[str, Any], n_devices: int, run_s: float, seed: int,
          outdir: Path) -> Dict[str, Any]:
    H.setup_paths()
    from policy import readiness as PR
    from policy import coordinator as PCO
    from policy import rollout as PRO

    calls: List[Dict[str, Any]] = []
    _inner = PR._state_value

    def inner(pf, device, rep, demand, h_s, qtype, link, deadline_s, omega_rc, in_episode,
              exclude_job, credit_allowed):
        got = _inner(pf, device, rep, demand, h_s, qtype, link, deadline_s, omega_rc,
                     in_episode, exclude_job, credit_allowed)
        calls.append(dict(site=_callsite(), value=float(got.get("value", 0.0)),
                          credit_allowed=bool(credit_allowed), rep=str(rep),
                          p_need=float(got.get("p_need", 0.0)),
                          u_here=float(got.get("u_here", 0.0)),
                          u_next=float(got.get("u_next_colder", 0.0)),
                          u_device=float(got.get("u_device", 0.0))))
        return got

    PR._state_value = inner

    # The wrapper is counted separately so cache HITS, which never reach `_state_value`, are
    # visible rather than silently absent from the call count.
    wrapper_calls = Counter()
    _wrap = PR.state_value

    def wrap(*a, **k):
        wrapper_calls[_callsite()] += 1
        return _wrap(*a, **k)

    # BOTH bindings, for the same reason the delta_j capture patches both: the coordinator holds
    # its own reference from module import and would otherwise be invisible.
    PR.state_value = wrap
    if getattr(PCO, "state_value", None) is not None:
        PCO.state_value = wrap

    cands: List[Dict[str, Any]] = []
    try:
        with H.capture_delta_j(cands):
            H.run_fleet_cell(outdir, n_devices, run_s=run_s, seed=seed,
                             arm_name="policy-core", switches=switches)
    finally:
        PR._state_value = _inner
        PR.state_value = _wrap
        if getattr(PCO, "state_value", None) is wrap:
            PCO.state_value = _wrap

    by_site: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for c in calls:
        by_site[c["site"]].append(c)

    sites = {}
    for site, cs in sorted(by_site.items()):
        vals = [c["value"] for c in cs]
        nz = sum(1 for v in vals if v == 0.0)
        sites[site] = dict(
            calls=len(cs),
            exactly_zero=nz,
            fraction_exactly_zero=round(nz / max(len(cs), 1), 4),
            distinct_values=len(set(round(v, 12) for v in vals)),
            example_values=sorted(set(round(v, 6) for v in vals))[:6],
            credit_allowed_true=sum(1 for c in cs if c["credit_allowed"]),
            credit_allowed_false=sum(1 for c in cs if not c["credit_allowed"]),
            p_need_zero=sum(1 for c in cs if c["p_need"] == 0.0),
            here_equals_floor=sum(1 for c in cs
                                  if c["u_here"] <= max(c["u_next"], c["u_device"])),
        )

    # The three quantities, over the SAME candidate population.
    sv_branch: List[float] = []
    sv_diff: List[float] = []
    for c in cands:
        if c.get("sv_delta") is not None:
            sv_diff.append(float(c["sv_delta"]))
        for k in ("sv_branch_a", "sv_branch_b"):
            if c.get(k) is not None:
                sv_branch.append(float(c[k]))

    return dict(
        switches=dict(switches),
        n_devices=n_devices, seed=seed, run_s=run_s,
        per_call=dict(total=len(calls), by_site=sites),
        wrapper_calls=dict(wrapper_calls),
        cache_hits=max(sum(wrapper_calls.values()) - len(calls), 0),
        per_branch_sum=dict(
            n=len(sv_branch),
            exactly_zero=sum(1 for v in sv_branch if v == 0.0),
            fraction_exactly_zero=(round(sum(1 for v in sv_branch if v == 0.0)
                                         / len(sv_branch), 4) if sv_branch else None)),
        between_branch_difference=dict(
            n=len(sv_diff),
            exactly_zero=sum(1 for v in sv_diff if v == 0.0),
            fraction_exactly_zero=(round(sum(1 for v in sv_diff if v == 0.0)
                                         / len(sv_diff), 4) if sv_diff else None),
            max_abs=(max(abs(v) for v in sv_diff) if sv_diff else None)),
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--n-devices", type=int, default=8)
    ap.add_argument("--run-s", type=float, default=300.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--base", default="planner_rc,plan_latest,replan,deficit_update,"
                                      "realistic_competing")
    a = ap.parse_args(argv)
    H.assert_dev_seed(a.seed)

    base = {s.strip(): True for s in a.base.split(",") if s.strip()}
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="covex_sv_"))

    conditions = {}
    for label, f2 in (("F2_off", False), ("F2_on", True)):
        sw = dict(base)
        sw["write_staleness"] = f2
        conditions[label] = probe(sw, a.n_devices, a.run_s, a.seed, tmp / label)
        print(label, "done", json.dumps(conditions[label]["per_call"]["by_site"])[:300],
              flush=True)

    out = dict(
        check="covex_harden_state_value_entrypoints",
        is_measurement=False,
        label="AUDIT. Which `state_value` entry point is authoritative, over ONE candidate "
              "population, in both F2 conditions. Nothing is fixed here; this only measures.",
        entry_point_note="`state_value` is a caching wrapper over `_state_value` and shadow mode "
                         "asserts they agree, so they cannot differ in VALUE. The reported "
                         "disagreements are between CALL SITES and between three different "
                         "quantities: per-call value, per-branch sum, between-branch difference.",
        conditions=conditions,
    )
    Path(a.out).write_text(json.dumps(out, indent=1))
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
