#!/usr/bin/env python3
"""D146 item 1: re-score every frozen-grid and sweep run under COMPLETION delivery (CPU only).

  python3 -I experiments/orchestration/live2/completion_delivery_rescore.py [jobs]

User ruling D146: a robot or single-shot answer counts as delivered at COMPLETION, prefill plus
decode, while a dashcam Yes/No may stay at first token. Generation settings are unchanged. Old
numbers are kept and labelled "first-token delivery".

WHAT THE COMMITTED RUNS ACTUALLY STAMP, verified rather than assumed. In every cell checked,
`outcomes.t_cloud_done` equals the request log's `t_first_token` EXACTLY, and `t_delivered` is that
plus a per-row constant forward delay. So the committed stamp is first-token based, which is what
section 12.3 of reports/study_frozen_test.md reported, and completion has to come from the request
log's `t_done`.

The new stamp is therefore, per outcome:

    t_delivered_completion = t_done + (t_delivered - t_cloud_done)

The forward delay is taken PER ROW rather than as a constant, so nothing is assumed about it; the
output records its distribution so a reader can see it is the 0.0222 s constant 12.3 identified.

A recall outcome with no matching cloud request was never sent (declined, or answered on the
device), so it has no completion time and is excluded from the flip count and reported separately.
Its on-time status cannot change under a delivery rule.
"""
from __future__ import annotations

import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "experiments/lib"))
import _provenance  # noqa: E402

RUNS = ROOT / "results/orchestration/live2/frozen_test/runs"
OUT = ROOT / "results/orchestration/live2/frozen_test/completion_delivery_rescore.json"
HEX = re.compile(r"^[0-9a-fA-F]{64}$")
SKIP = ("REFUSED", "ABORTED", "SKIPPED", "STOPPED")


def kind_of(qid):
    """robot (S-EMBER / LH-REQ, a 64-hex digest) against single shot ("<dataset>/<id>")."""
    if qid is None:
        return "other"
    return "robot" if HEX.match(str(qid)) else ("single_shot" if "/" in str(qid) else "other")


def one(run: Path):
    o_p, r_p = run / "outcomes.jsonl.gz", run / "request.jsonl.gz"
    if not (o_p.exists() and r_p.exists()):
        return run.name, None
    req = {}
    with gzip.open(r_p, "rt") as fh:
        for ln in fh:
            r = json.loads(ln)
            if r.get("opportunity_id"):
                req[r["opportunity_id"]] = r
    rows, fwd = [], []
    stamp_ok, stamp_bad, stamp_unknown = 0, 0, 0
    with gzip.open(o_p, "rt") as fh:
        for ln in fh:
            o = json.loads(ln)
            if not o.get("question_id") or o.get("within_L") is None:
                continue
            q = req.get(o.get("opportunity_id"))
            dl = float(o["t_opportunity"]) + float(o["deadline_s"])
            if o.get("t_delivered") is None:
                # never delivered at all, so no delivery RULE can change its status. Counted
                # separately rather than coerced to a number, because a missing stamp and a late
                # one are different events and merging them would hide the first.
                rows.append(dict(kind=kind_of(o["question_id"]), old_on=False, new_on=False,
                                 never_sent=True, never_delivered=True))
                continue
            old_on = float(o["t_delivered"]) <= dl
            if q is None or q.get("t_done") is None or o.get("t_cloud_done") is None:
                rows.append(dict(kind=kind_of(o["question_id"]), old_on=old_on,
                                 new_on=old_on, never_sent=True))
                continue
            if q.get("t_first_token") is None:
                stamp_unknown += 1
            elif abs(float(o["t_cloud_done"]) - float(q["t_first_token"])) <= 1e-6:
                stamp_ok += 1
            else:
                stamp_bad += 1
            f = float(o["t_delivered"]) - float(o["t_cloud_done"])
            fwd.append(f)
            new_on = (float(q["t_done"]) + f) <= dl
            rows.append(dict(kind=kind_of(o["question_id"]), old_on=old_on, new_on=new_on,
                             never_sent=False,
                             slack_old=round(dl - float(o["t_delivered"]), 4),
                             slack_new=round(dl - (float(q["t_done"]) + f), 4),
                             decode_s=(None if q.get("t_first_token") is None else
                                       round(float(q["t_done"])
                                             - float(q["t_first_token"]), 4))))
    sent = [r for r in rows if not r["never_sent"]]
    rec = dict(
        n_outcomes=len(rows), n_sent=len(sent), n_never_sent=len(rows) - len(sent),
        forward_delay=dict(n=len(fwd), min=(min(fwd) if fwd else None),
                           max=(max(fwd) if fwd else None),
                           constant=bool(fwd and max(fwd) - min(fwd) < 1e-9)),
        stamp_is_first_token=dict(matches=stamp_ok, mismatches=stamp_bad,
                                  no_first_token_recorded=stamp_unknown,
                                  verified=bool(stamp_bad == 0 and stamp_ok > 0)),
        by_kind={})
    for k in ("robot", "single_shot", "other"):
        sel = [r for r in rows if r["kind"] == k]
        if not sel:
            continue
        s2 = [r for r in sel if not r["never_sent"]]
        rec["by_kind"][k] = dict(
            n=len(sel), n_sent=len(s2),
            n_never_delivered=sum(1 for r in sel if r.get("never_delivered")),
            on_time_first_token=sum(1 for r in sel if r["old_on"]),
            on_time_completion=sum(1 for r in sel if r["new_on"]),
            flips_to_late=sum(1 for r in sel if r["old_on"] and not r["new_on"]),
            flips_to_on_time=sum(1 for r in sel if not r["old_on"] and r["new_on"]),
            decode_s_p50=(sorted(r["decode_s"] for r in s2 if r.get("decode_s") is not None)
                          [len([1 for r in s2 if r.get("decode_s") is not None]) // 2]
                          if any(r.get("decode_s") is not None for r in s2) else None),
            decode_s_max=(max((r["decode_s"] for r in s2
                               if r.get("decode_s") is not None), default=None)))
    rec["flips_total"] = sum(v["flips_to_late"] + v["flips_to_on_time"]
                             for v in rec["by_kind"].values())
    return run.name, rec


def main():
    jobs = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    dirs = sorted(p for p in RUNS.iterdir()
                  if p.is_dir() and not any(s in p.name for s in SKIP)
                  and (p / "outcomes.jsonl.gz").exists())
    import multiprocessing as mp
    with mp.Pool(jobs) as pool:
        got = {k: v for k, v in pool.imap_unordered(one, dirs) if v is not None}
    tot = Counter()
    for v in got.values():
        for k, b in v["by_kind"].items():
            tot[f"{k}_flips_to_late"] += b["flips_to_late"]
            tot[f"{k}_flips_to_on_time"] += b["flips_to_on_time"]
            tot[f"{k}_n"] += b["n"]
    res = dict(
        label="D146 item 1: every frozen-grid and sweep run re-scored under COMPLETION delivery "
              "for robot and single-shot answers; dashcam unchanged at first token. Old values are "
              "carried beside the new ones under the name first-token delivery. CPU only; no "
              "model, no GPU, no rerun.",
        at=datetime.now().isoformat(), n_runs=len(got),
        rule="t_delivered_completion = t_done + (t_delivered - t_cloud_done), the forward delay "
             "taken per row rather than assumed",
        stamp_verification=dict(
            runs_where_t_cloud_done_equals_first_token=sum(
                1 for v in got.values() if v["stamp_is_first_token"]["verified"]),
            runs_with_any_mismatch=sum(
                1 for v in got.values() if v["stamp_is_first_token"]["mismatches"])),
        totals=dict(tot), runs=got)
    res["_provenance"] = _provenance.stamp(script="completion_delivery_rescore.py",
                                           model="none", device="cpu", n=len(got), args=None)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1))
    print(f"{len(got)} runs re-scored")
    print(f"  stamp verified as first-token in "
          f"{res['stamp_verification']['runs_where_t_cloud_done_equals_first_token']} runs, "
          f"mismatches in {res['stamp_verification']['runs_with_any_mismatch']}")
    for k in sorted(tot):
        print(f"  {k}: {tot[k]}")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
