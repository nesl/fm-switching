#!/usr/bin/env python3
"""D133 (ruled 2026-11-19): robot headline = p 0.90 within 5 s over FEASIBLE questions, matched per opportunity_id;
the all-questions figure is reported beside it. Feasibility is a property of the TRACE, not the arm.

The rule is flash's `policy/audit/feasibility_ceiling.py` (0cb1195), applied per question with the same committed
functions and nothing changed: feasible iff
    costs.recall_ttft_s(h, "COLD") + costs.recall_ttft_s(h, "GPU-WARM") + traces.RTT_MS / 1000 <= deadline_s,
h = the trace record's `history_tokens` (history at question time). That script keeps only per-cell counts, so this
one emits the per-opportunity verdicts and REQUIRES its per-cell counts to equal the committed
`feasibility_ceiling.json` before any run is scored.

Usage: python feasible_on_time.py <live_runs dir> <traces dir> <out json>
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
for p in (HERE.parent, HERE.parent / "fleet", REPO / "experiments/orchestration/baselines",
          REPO / "experiments/orchestration/sim", REPO / "experiments/lib"):
    sys.path.insert(0, str(p))
import costs as C          # noqa: E402
import traces as TRC       # noqa: E402

COMMITTED = REPO / "results/orchestration/live2/covex_harden/feasibility_ceiling.json"


def verdicts(trace_jsonl: Path):
    link = TRC.RTT_MS / 1000.0
    out = {}
    for line in open(trace_jsonl):
        d = json.loads(line)
        if d.get("kind") != "recall_question":
            continue
        h = int(d.get("history_tokens") or 0)
        dl = float(d.get("deadline_s") or 5.0)
        tot = C.recall_ttft_s(h, "COLD") + C.recall_ttft_s(h, "GPU-WARM") + link
        out[d["opportunity_id"]] = dict(h=h, total_s=round(tot, 4), deadline_s=dl, feasible=bool(tot <= dl))
    return out


def main(runs_dir, traces_dir, out_path):
    committed = {(c["seed"], c["n_devices"]): c for c in json.loads(COMMITTED.read_text())["cells"]}
    cache, recon, rows, invalid = {}, {}, [], []
    for cell in sorted(Path(runs_dir).glob("*/cell.json")):
        name = cell.parent.name
        if "REFUSED" in name or "ABORTED" in name:
            continue
        c = json.loads(cell.read_text())
        if not (c.get("err") is None and c.get("run_valid") is True and c.get("digests_equal") is True
                and (c.get("n_errors") if c.get("n_errors") is not None else 1) == 0):
            invalid.append(name)                     # never used (CLAUDE.md: never use INVALID results)
            continue
        seed, n = int(c["seed"]), int(c["n_devices"])
        key = (seed, n)
        if key not in cache:
            tp = Path(traces_dir) / ("seed%d_n%d_600s_A" % (seed, n)) / "trace.jsonl"
            cache[key] = verdicts(tp)
            nf = sum(1 for v in cache[key].values() if v["feasible"])
            ref = committed.get(key)
            recon[str(key)] = dict(n_questions=len(cache[key]), n_feasible=nf,
                                   committed_n_questions=(ref or {}).get("n_questions"),
                                   committed_n_feasible=(ref or {}).get("n_feasible"),
                                   match=bool(ref and ref["n_questions"] == len(cache[key]) and ref["n_feasible"] == nf))
        V = cache[key]
        ont = {}
        for line in open(cell.parent / "outcomes.jsonl"):
            o = json.loads(line)
            if o.get("kind") == "recall":
                # the run scorer's rule: on time iff DELIVERED within the question's own deadline
                # (t_delivered - t_opportunity <= deadline_s); cloud_payload.on_time counts at cloud completion and
                # disagrees for answers delivered just after the deadline
                td = o.get("t_delivered")
                ont[o["opportunity_id"]] = bool(td is not None and float(td) - float(o["t_opportunity"])
                                                <= float(o.get("deadline_s") or 5.0))
        feas = [k for k, v in V.items() if v["feasible"]]
        missing = [k for k in V if k not in ont]
        rows.append(dict(run=name, seed=seed, n=n, n_questions=len(V), n_feasible=len(feas),
                         on_time_all=sum(1 for k in V if ont.get(k)), on_time_feasible=sum(1 for k in feas if ont.get(k)),
                         frac_all=round(sum(1 for k in V if ont.get(k)) / max(len(V), 1), 4),
                         frac_feasible=round(sum(1 for k in feas if ont.get(k)) / max(len(feas), 1), 4),
                         robot_feasible_meets_090=bool(sum(1 for k in feas if ont.get(k)) >= 0.90 * len(feas)),
                         questions_without_outcome=len(missing),
                         infeasible_on_time=sum(1 for k in V if not V[k]["feasible"] and ont.get(k)),
                         scorer_on_time_all=c["score"]["score"]["sweep"][0].get("robot_pool_on_time"),
                         matches_scorer=(c["score"]["score"]["sweep"][0].get("robot_pool_on_time")
                                         == sum(1 for k in V if ont.get(k)))))
    res = dict(rule="flash policy/audit/feasibility_ceiling.py (0cb1195) per opportunity_id; D133 ruled 2026-11-19",
               reconciliation_with_committed=recon, all_cells_match=all(r["match"] for r in recon.values()),
               all_runs_match_scorer=all(r["matches_scorer"] for r in rows), invalid_runs_excluded=invalid, runs=rows)
    Path(out_path).write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(dict(all_cells_match=res["all_cells_match"], all_runs_match_scorer=res["all_runs_match_scorer"])))
    for r in rows:
        print(r["run"], r["on_time_feasible"], "/", r["n_feasible"], "feasible;", r["on_time_all"], "/", r["n_questions"], "all;",
              "missing", r["questions_without_outcome"], "infeasible on time", r["infeasible_on_time"])


if __name__ == "__main__":
    main(*sys.argv[1:4])
