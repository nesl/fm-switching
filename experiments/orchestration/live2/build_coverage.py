#!/usr/bin/env python3
"""History-size fix check (StudyLIVE2 acceptance on the D114 build, and every pilot run). CPU only, after the server
stops.

For every robot BUILD request (a whole rebuild or a piece: a request with a session and no opportunity) it reports:
  - the build's prompt tokens (the chain's cumulative prefix after this build, for a piece);
  - the history the trace says that session held when the build was released: the `cum_tokens` of the session's last
    history record (preload or batch) captured at or before the release, and of the last one before the NEXT batch,
    which bounds a batch still on the uplink;
  - the next recall on the same session: its prompt and cached tokens.
A WHOLE build covers its history when its prompt is within one history batch (plus the header) of the trace's
cumulative size at release; the next recall's cached tokens should then equal the build's prompt (less its last
partial block). Before the fix a whole build covered max(preload, one batch).
Also counts robot questions, cloud-answered and on time.
"""
import json
import sys
from pathlib import Path


def jl(p):
    return [json.loads(l) for l in open(p)]


def check(run_dir: Path, trace_dir: Path):
    req = jl(run_dir / "request.jsonl")
    dec = {d["decision_id"]: d for d in jl(run_dir / "decision.jsonl")}
    out = jl(run_dir / "outcomes.jsonl")
    tr = [r for r in jl(trace_dir / "trace.jsonl") if r["kind"] in ("history_preload", "history_batch")]
    by_s = {}
    for r in tr:
        by_s.setdefault(r["session_id"], []).append(r)
    for v in by_s.values():
        v.sort(key=lambda r: r["t"])
    rows = []
    for r in req:
        if not r.get("session_id") or r.get("opportunity_id"):
            continue
        k = (dec.get(r["decision_id"]) or {}).get("kind")
        hist = by_s.get(r["session_id"], [])
        upto = [h for h in hist if h["t"] <= r["t_submit"] + 1e-9]
        cum = upto[-1].get("cum_tokens", None) if upto else 0
        batch = (upto[-1].get("est_tokens") if upto else 0) or 0
        nxt = sorted((x for x in req if x.get("session_id") == r["session_id"] and x.get("opportunity_id")
                      and x["t_submit"] >= r["t_submit"]), key=lambda x: x["t_submit"])
        n = nxt[0] if nxt else None
        whole = k == "release_whole"
        ok = None
        if whole and cum:
            ok = (r["prompt_tokens"] >= cum - batch - 64) and (r["prompt_tokens"] <= cum + batch + 400)
        rows.append(dict(request_id=r["request_id"], kind=k, session_id=r["session_id"], t_submit=r["t_submit"],
                         prompt_tokens=r["prompt_tokens"], cached_tokens=r["cached_tokens"], trace_cum_tokens=cum,
                         ratio=(round(r["prompt_tokens"] / cum, 4) if cum else None), last_batch_tokens=batch,
                         next_recall_prompt=(n["prompt_tokens"] if n else None),
                         next_recall_cached=(n["cached_tokens"] if n else None), covers=ok))
    rq = [o for o in out if o["kind"] == "recall"]
    wholes = [x for x in rows if x["kind"] == "release_whole"]
    return dict(n_builds=len(rows), n_whole=len(wholes),
                n_whole_covering=sum(1 for x in wholes if x["covers"]),
                n_whole_not_covering=sum(1 for x in wholes if x["covers"] is False),
                whole_ratio_min=min((x["ratio"] for x in wholes if x["ratio"]), default=None),
                robot_questions=len(rq),
                robot_cloud_answered=sum(1 for o in rq if (o.get("cloud_payload") or {}).get("request_id")),
                robot_on_time=sum(1 for o in rq if o["within_L"]),
                builds=rows)


if __name__ == "__main__":
    run_dir, trace_dir = Path(sys.argv[1]), Path(sys.argv[2])
    res = check(run_dir, trace_dir)
    (run_dir / "build_coverage.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "builds"}))
