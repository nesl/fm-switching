#!/usr/bin/env python3
"""StudyFROZEN-test, D144: rescore runs scored before the three-type scorer fix (41b0eae) and add the D133 feasible-question
column to every kept three-type run. Run only when no live driver is active (the run preflight refuses on host Python).

Feasibility is flash's rule (policy/audit/feasibility_ceiling.py, 0cb1195), applied per ROBOT question from the run's own
trace: feasible iff costs.recall_ttft_s(h, "COLD") + costs.recall_ttft_s(h, "GPU-WARM") + traces.RTT_MS / 1000 <= deadline,
h = the question's history_tokens at question time. Assistive (single-shot) questions are excluded from the robot pool
(their device ids start "asst"). On time = DELIVERED within the deadline (the scorer's rule), so a dropped or over-context
request is a miss (D144). Per-run error count and requests offered are recorded; saturated if > 5 percent errored.

Usage: python frozen_rescore_feasible.py <runs dir> <out json>
"""
import gzip
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for p in (HERE, HERE / "fleet", HERE / "scorer", REPO / "experiments/orchestration/baselines",
          REPO / "experiments/orchestration/sim", REPO / "experiments/lib"):
    sys.path.insert(0, str(p))
import costs as C          # noqa: E402
import traces as TRC       # noqa: E402
import score as SC         # noqa: E402

CAL = REPO / "results/orchestration/live2/calibration/live2_calibration_dense_jpeg.json"


def jl(p: Path):
    op = gzip.open if p.suffix == ".gz" else open
    with op(p, "rt") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def first(d: Path, stem: str) -> Path:
    for c in (d / stem, d / (stem + ".gz")):
        if c.exists():
            return c
    raise FileNotFoundError(d / stem)


def main(runs_dir, out_path):
    link = TRC.RTT_MS / 1000.0
    rows = []
    for cell in sorted(Path(runs_dir).glob("*/cell.json")):
        d = cell.parent
        if any(t in d.name for t in ("REFUSED", "ABORTED")):
            continue
        c = json.loads(cell.read_text())
        if not (c.get("err") is None and c.get("run_valid") is True and c.get("digests_equal") is True):
            continue
        tdir = Path(c["trace_dir"])
        rescored = False
        if not (c.get("score") or {}).get("ok"):
            raw = Path.home() / "data/live2/frozen_grid/runs" / d.name      # uncompressed copy (the committed one gzips logs)
            try:
                c["score"] = dict(ok=True, score=SC.score_run(tdir, raw if raw.exists() else d, CAL, c["arm"]),
                                  rescored="D144: rescored with the three-type scorer (41b0eae)")
            except Exception as e:                                                 # noqa: BLE001
                c["score"] = dict(ok=False, error=f"{type(e).__name__}: {e}", rescored="D144 rescore failed")
            cell.write_text(json.dumps(c, indent=1, default=str) + "\n")
            if raw.exists() and (raw / "cell.json").exists():
                (raw / "cell.json").write_text(json.dumps(c, indent=1, default=str) + "\n")
            rescored = True
        feas = {}
        for r in jl(first(tdir, "trace.jsonl")):
            if r.get("kind") != "recall_question" or not str(r.get("device_id", "")).startswith("robo"):
                continue
            h = int(r.get("history_tokens") or 0)
            dl = float(r.get("deadline_s") or 5.0)
            feas[r["opportunity_id"]] = (C.recall_ttft_s(h, "COLD") + C.recall_ttft_s(h, "GPU-WARM") + link) <= dl
        ont = {}
        for o in jl(first(d, "outcomes.jsonl")):
            if o.get("kind") == "recall" and o["opportunity_id"] in feas:
                td = o.get("t_delivered")
                ont[o["opportunity_id"]] = bool(td is not None and float(td) - float(o["t_opportunity"])
                                                <= float(o.get("deadline_s") or 5.0))
        fq = [k for k, v in feas.items() if v]
        sw = (((c.get("score") or {}).get("score") or {}).get("sweep") or [{}])[0]
        nreq, nerr = c.get("n_requests"), c.get("n_errors")
        rows.append(dict(run=d.name, arm=c["arm"], n=c["n_devices"], seed=c["seed"], rescored=rescored,
                         score_ok=bool((c.get("score") or {}).get("ok")),
                         robot_questions=len(feas), robot_feasible=len(fq),
                         robot_on_time_all=sum(1 for k in feas if ont.get(k)),
                         robot_on_time_feasible=sum(1 for k in fq if ont.get(k)),
                         scorer_robot_on_time=sw.get("robot_pool_on_time"), scorer_robot_n=sw.get("robot_pool_n"),
                         matches_scorer=(sw.get("robot_pool_on_time") == sum(1 for k in feas if ont.get(k))),
                         dashcam_all_meet=sw.get("dashcam_all_meet"), capacity_met=sw.get("capacity_met"),
                         ss_on_time=sw.get("ss_pool_on_time"), ss_n=sw.get("ss_pool_n"),
                         request_errors=nerr, requests_offered=nreq,
                         saturated=(None if not nreq else (nerr or 0) / nreq > 0.05)))
    res = dict(rule="flash feasibility_ceiling.py (0cb1195) per robot question; on time = delivered within deadline; D144 "
                    "misses for dropped and over-context requests; saturated if > 5 percent of requests errored",
               all_match_scorer=all(r["matches_scorer"] for r in rows if r["score_ok"]), runs=rows)
    Path(out_path).write_text(json.dumps(res, indent=1, default=str) + "\n")
    for r in rows:
        print(r["run"], "feasible", r["robot_on_time_feasible"], "/", r["robot_feasible"], "all", r["robot_on_time_all"], "/",
              r["robot_questions"], "scorer", r["scorer_robot_on_time"], "rescored" if r["rescored"] else "",
              "SATURATED" if r["saturated"] else "")
    print("all_match_scorer", res["all_match_scorer"])


if __name__ == "__main__":
    main(*sys.argv[1:3])
