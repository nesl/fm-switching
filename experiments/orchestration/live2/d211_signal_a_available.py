#!/usr/bin/env python3
"""D211 signal (a), IN THE ONLY FORM AVAILABLE ON COMMITTED DATA, and labelled as such.

WHAT D211 ASKS FOR AND WHY IT CANNOT BE COMPUTED AS WRITTEN. The ruled signal is
`host_tokens = max(0, cached_tokens - gpu_prefix_believed)`. `cached_tokens` is recorded per
request. `gpu_prefix_believed` IS NOT: the schema field for it, `belief.gpu_tokens_by_session`
(schema.py:316), is EMPTY on every decision row of every reported arm, because its only producer is
`arms_policy.py:1067-1075` and the reported covex-v6 ladder never enters `arms_policy.py` (the
StudyPLACEHOLDER-TRIAGE structural fact S1). It could be reconstructed by accumulating
`release_piece.piece_tokens` per session and resetting on an EVICT, but that is a declared proxy
and NOTHING CAN VALIDATE IT, because no committed cell carries the aggregate host counter either.
Consistency check 6 forbids a questionable proxy in a headline, and there the proxy would BE the
headline.

WHAT THIS COMPUTES INSTEAD, which needs no reconstruction and no proxy. The belief's TIER at
submission IS recorded (`residency.jsonl`), so the two directions of belief error can be counted
exactly:

  BELIEF TOO OPTIMISTIC   believed_tier == "gpu" and cached_tokens == 0
                          the belief claimed GPU residency the engine did not honour
  RESIDENCY THE BELIEF CANNOT SEE   believed_tier == "cold" and cached_tokens > 0
                          the engine reused a prefix the belief had written off. On this engine a
                          hit can be GPU or host and cannot be told apart per request, so this is
                          an UPPER BOUND on unobserved host residency and not a measurement of it.
                          It is nonetheless the quantity D211 exists about, and it is exact.

Both are NECESSARY-NOT-SUFFICIENT forms of the ruled quantity and are labelled UNVALIDATED, as the
sequencing ruling requires. Neither is a substitute for signal (a), and neither is used to decide
anything: the pre-registered bar is untouched and no belief or price is changed by this script.
"""
from __future__ import annotations

import argparse
import bisect
import gzip
import json
import statistics as st
import subprocess
from pathlib import Path
from typing import Any, Dict, List


def git_show(rev: str, path: str) -> bytes:
    return subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True,
                          cwd="/home/pragya/Desktop/FM-switching", check=True).stdout


def rows(rev: str, path: str) -> List[Dict[str, Any]]:
    raw = git_show(rev, path)
    if path.endswith(".gz"):
        raw = gzip.decompress(raw)
    return [json.loads(l) for l in raw.decode().splitlines() if l.strip()]


def quant(v: List[float]) -> Dict[str, Any]:
    if not v:
        return {"n": 0}
    s = sorted(v)
    def q(p):
        return s[min(len(s) - 1, int(p * len(s)))]
    return {"n": len(s), "min": s[0], "p10": q(.10), "p25": q(.25), "p50": q(.50),
            "p75": q(.75), "p90": q(.90), "max": s[-1], "mean": round(st.fmean(s), 3),
            "n_zero": sum(1 for x in s if x == 0), "n_distinct": len(set(s))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", required=True)
    ap.add_argument("--cell", required=True, help="path of the run dir inside the repo")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    req = rows(a.rev, a.cell + "/request.jsonl.gz")
    res = rows(a.rev, a.cell + "/residency.jsonl")
    dec = rows(a.rev, a.cell + "/decision.jsonl.gz")

    # the ruled signal's missing input, counted rather than asserted
    gpu_tok_nonempty = sum(1 for r in dec if (r.get("belief") or {}).get("gpu_tokens_by_session"))

    by_sess: Dict[str, List[Any]] = {}
    for r in res:
        by_sess.setdefault(r["session_id"], []).append((float(r["t"]), r["believed_tier"],
                                                        r.get("telemetry_cached_tokens")))
    for k in by_sess:
        by_sess[k].sort()
    times = {k: [x[0] for x in v] for k, v in by_sess.items()}

    def tier_at(sid: str, t: float):
        v = by_sess.get(sid)
        if not v:
            return None, None
        i = bisect.bisect_right(times[sid], t) - 1
        if i < 0:
            return None, None
        return v[i][1], v[i][2]

    joined = []
    for r in req:
        sid = r.get("session_id")
        ct = r.get("cached_tokens")
        if not sid or ct is None or r.get("http_status") not in (200, None):
            continue
        tier, tele = tier_at(sid, float(r["t_submit"]))
        if tier is None:
            continue
        joined.append({"tier": tier, "cached_tokens": int(ct),
                       "prompt_tokens": int(r.get("prompt_tokens") or 0),
                       "cached_fraction": r.get("cached_fraction"),
                       "cache_path": r.get("cache_path")})

    out: Dict[str, Any] = {
        "_register": "OBSERVED join of committed per-request usage with the committed residency log. UNVALIDATED: no aggregate host counter exists for this cell, so the pre-registered agreement bar cannot be evaluated here.",
        "_not_the_ruled_signal": "the ruled signal (a) needs belief.gpu_tokens_by_session, which is EMPTY on every decision row (see below). These are the two exact belief-error directions that need no reconstruction.",
        "cell": a.cell, "rev": a.rev,
        "decision_rows": len(dec),
        "decision_rows_with_nonempty_gpu_tokens_by_session": gpu_tok_nonempty,
        "requests_in_cell": len(req), "requests_joined_to_a_belief": len(joined),
        "coverage": (round(len(joined) / len(req), 4) if req else None),
        "by_believed_tier": {},
    }
    for tier in ("gpu", "host", "cold"):
        sub = [j for j in joined if j["tier"] == tier]
        out["by_believed_tier"][tier] = {
            "n": len(sub),
            "cached_tokens": quant([float(j["cached_tokens"]) for j in sub]),
            "prompt_tokens": quant([float(j["prompt_tokens"]) for j in sub]),
            "n_cached_zero": sum(1 for j in sub if j["cached_tokens"] == 0),
            "n_cached_nonzero": sum(1 for j in sub if j["cached_tokens"] > 0),
        }
    g = out["by_believed_tier"]["gpu"]
    c = out["by_believed_tier"]["cold"]
    out["belief_too_optimistic"] = {
        "_definition": "believed gpu at submission, engine reused 0 prompt tokens",
        "n": g["n_cached_zero"], "of": g["n"],
        "fraction": (round(g["n_cached_zero"] / g["n"], 4) if g["n"] else None)}
    out["residency_the_belief_cannot_see"] = {
        "_definition": "believed cold at submission, engine reused > 0 prompt tokens. UPPER BOUND on unobserved host residency: this engine cannot separate a GPU hit from a host hit per request.",
        "n": c["n_cached_nonzero"], "of": c["n"],
        "fraction": (round(c["n_cached_nonzero"] / c["n"], 4) if c["n"] else None),
        "cached_tokens_when_it_happens": quant([float(j["cached_tokens"]) for j in joined
                                                if j["tier"] == "cold" and j["cached_tokens"] > 0])}
    Path(a.out).write_text(json.dumps(out, indent=1, default=float) + "\n")
    print(json.dumps({k: out[k] for k in
                      ("requests_in_cell", "requests_joined_to_a_belief", "coverage",
                       "decision_rows_with_nonempty_gpu_tokens_by_session",
                       "belief_too_optimistic", "residency_the_belief_cannot_see")},
                     indent=1, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
