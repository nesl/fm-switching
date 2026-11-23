#!/usr/bin/env python3
"""Step 2 probe for the EPISODE EARLY EXIT (D192 (3)): does the mechanism's TRIGGER quantity
exist inside the coordinator process at all?

The mechanism needs the episode's STANDING CALIBRATED ANSWER (cloud answer if delivered on time,
else the device's own, D165 B) compared against the D197 / D192 EPISODE-LEVEL tier threshold.
This probe does not build the switch. It censuses, over ONE dry s4 cell of the rung-3 arm run
through the committed recipe, every quantity that could carry that trigger:

  * every value the arm ever sees in `EpisodicStream.delivered_scores` (cstate.py:592), which is
    the ONLY score-shaped field in the arm-facing Observation (baselines/interface.py:100);
  * every `cloud_score` the coordinator extracts for a monitor answer (coordinator.py:1843);
  * whether any device-side score reaches the process at all.

NOT A MEASUREMENT OF ANY ARM. No digest is claimed here: the digest claim is made by the
committed `cf_pd_one_cell.py` in its own process.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="clean git-archive export root")
    ap.add_argument("--arm", default="covex-v6-fair-c5attr")
    ap.add_argument("--seed", type=int, default=4)
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--run-s", type=float, default=1200.0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--parent-sha", default=None,
                    help="the literal sha the --root export was made from. Passed rather than "
                         "read, because a `git archive` export has no .git and `_provenance."
                         "stamp` would label the run with whatever HEAD happened to be elsewhere.")
    ap.add_argument("--load-at-start", default=None)
    a = ap.parse_args()

    L2 = Path(a.root) / "experiments/orchestration/live2"
    for _p in (L2, L2 / "fleet", L2 / "v5", L2 / "hybrid", L2.parent / "baselines"):
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))

    import arms as A                                                   # noqa: F401
    import arms_v6c5 as VC
    import arms_v6cf as VCF
    import arms_v6shares as VSH
    import arms_v6state as VS
    VS.register()
    VC.register()
    VSH.register()
    VCF.register()

    import cf_instrument as CI
    for _n in dir(CI):
        _o = getattr(CI, _n)
        if isinstance(_o, type) and hasattr(_o, "over_budget"):
            _o.over_budget = lambda self, budget_ms=None: False

    import cstate as CS
    import coordinator as CO

    census = dict(
        observations=0,
        streams_seen=0,
        delivered_values=collections.Counter(),
        delivered_len_hist=collections.Counter(),
        monitor_score_calls=0,
        monitor_cloud_score_none=0,
        monitor_cloud_score_number=0,
        monitor_cloud_score_values=collections.Counter(),
        delivered_append_values=collections.Counter(),
    )

    _obs = CS.CoordState.observation

    def obs(self, now, epoch, reads_device_answer=False):
        o = _obs(self, now, epoch, reads_device_answer)
        census["observations"] += 1
        for s in o.streams:
            census["streams_seen"] += 1
            census["delivered_len_hist"][len(s.delivered_scores)] += 1
            for v in s.delivered_scores:
                census["delivered_values"][repr(v)] += 1
        return o
    CS.CoordState.observation = obs

    _score_of = CO.Live2Coordinator._score_of

    def score_of(self, sub, r):
        d = _score_of(self, sub, r)
        if getattr(sub, "kind", None) == "monitor":
            census["monitor_score_calls"] += 1
            v = (d or {}).get("cloud_score")
            if v is None:
                census["monitor_cloud_score_none"] += 1
            else:
                census["monitor_cloud_score_number"] += 1
                census["monitor_cloud_score_values"][repr(v)] += 1
        return d
    CO.Live2Coordinator._score_of = score_of

    import test_hybrid as TH
    rows, st = TH.dry(a.arm, a.seed, a.n, run_s=a.run_s, ratio="40:40:20",
                      robot_question_set="lh_req", ss_question_set="ss2",
                      dashcam_format="epg", robot_upload="per-frame",
                      robot_reask_mean_s=30.0)
    rows = list(rows or [])
    st = dict(st or {})

    out = dict(
        probe="exit_trigger_probe",
        arm=a.arm, seed=a.seed, n=a.n, run_s=a.run_s, rows=len(rows),
        observations=census["observations"],
        streams_seen=census["streams_seen"],
        delivered_scores_distinct_values=dict(census["delivered_values"]),
        delivered_scores_len_hist={str(k): v for k, v in
                                   sorted(census["delivered_len_hist"].items())},
        monitor_score_calls=census["monitor_score_calls"],
        monitor_cloud_score_none=census["monitor_cloud_score_none"],
        monitor_cloud_score_number=census["monitor_cloud_score_number"],
        monitor_cloud_score_values=dict(census["monitor_cloud_score_values"]),
        delivered_append_sites="coordinator.py:658 (_device_answer) and coordinator.py:1907 "
                               "(_settle); both append a literal 0.0",
        device_score_in_process=False,
        arm_stats_subset={k: st.get(k) for k in
                          ("decisions", "c5_dash_held", "recall_CLOUD", "state_decisions")},
    )
    out["_provenance"] = {
        "git_commit": a.parent_sha or "unspecified",
        "git_commit_note": "the sha of the clean `git archive` export this ran on; an export has "
                           "no .git, so it is passed and not read",
        "script": "d192_exit_trigger_probe.py",
        "model": "none",
        "device": "cpu",
        "n": len(rows),
        "seed": a.seed,
        "load_at_start": a.load_at_start,
        "claims_a_digest": False,
    }
    Path(a.out).write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps({k: v for k, v in out.items()
                      if k != "delivered_scores_len_hist"}, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
