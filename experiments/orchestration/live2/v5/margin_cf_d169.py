"""MARGIN_CF over the D169 population. CPU only. Computed AFTER P_hat was frozen and the
population committed, in that order."""
import gzip, json, shutil, statistics as st, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIVE2 = HERE.parent
REPO = LIVE2.parents[2]
for p in (str(LIVE2), str(LIVE2 / "fleet"), str(LIVE2 / "scorer"), str(HERE),
          str(REPO / "experiments/orchestration/baselines"), str(REPO / "experiments/lib"),
          str(REPO / "experiments/orchestration")):
    if p not in sys.path:
        sys.path.insert(0, p)

import cost_model_gate_d162 as G          # noqa: E402
import cf_ontime_d162 as P                # noqa: E402
import trace as TR                        # noqa: E402

POP = REPO / "results/orchestration/live2/v5/margin_cf_population_d169.json"
OUT = REPO / "results/orchestration/live2/v5/margin_cf_d169.json"
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
A_D2_DEV = 0.250
MIN_N, MIN_WARM = 40, 40


def main():
    pop = json.loads(POP.read_text())
    payload = P.load()                     # verifies BOTH hashes, raises if either moved
    rows, per_cell = [], {}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for c in pop["cells"]:
            cell = RUNS / c["cell"]
            meta = json.loads((cell / "run_meta.json").read_text())
            b = TR.generate_trace(c["seed"], 16, "40:40:20", 1200.0, "A",
                                  robot_question_set="lh_req", ss_question_set="ss2",
                                  dashcam_format="epg", robot_upload="per-frame",
                                  robot_reask_mean_s=30.0)
            tdir = td / ("t_" + c["cell"])
            tm = TR.write_trace(tdir, b)
            if str(tm.get("fairness_digest")) != str(meta.get("trace_fairness_digest")):
                per_cell[c["cell"]] = dict(error="trace digest mismatch; cell SKIPPED")
                continue
            feats = {}
            for r in G.features(cell):
                feats.setdefault(r["i"], r)
            G.classify(list(feats.values()))
            # robot questions RELEASED: a request carrying the opportunity of a robo outcome
            outs = G.jl(cell / "outcomes.jsonl")
            robq = {str(o.get("opportunity_id")): o for o in outs
                    if str(o.get("session_id") or "").startswith("robo")}
            reqs = G.jl(cell / "request.jsonl")
            by_opp = {}
            for rq in reqs:
                oid = str(rq.get("opportunity_id") or "")
                if oid in robq and rq.get("t_submit") is not None:
                    by_opp.setdefault(oid, []).append(rq)
            zone = {}
            for r in feats.values():
                zone[int(r["t_submit"] // 100.0)] = r["zone"]
            n_h = n_skip = 0
            for oid, rl in by_opp.items():
                rq = min(rl, key=lambda x: float(x["t_submit"]))
                z = zone.get(int(float(rq["t_submit"]) // 100.0))
                if z != "healthy":
                    continue
                o = robq[oid]
                ft = feats.get(next((k for k, v in feats.items()
                                     if abs(v["t_submit"] - float(rq["t_submit"])) < 1e-9), None))
                if ft is None or rq.get("prompt_tokens") is None or rq.get("cached_tokens") is None:
                    n_skip += 1
                    continue
                dl = o.get("deadline_abs_s")
                if dl is None and o.get("t_opportunity") is not None:
                    dl = float(o["t_opportunity"]) + float(o.get("deadline_s") or 3.0)
                if dl is None:
                    n_skip += 1
                    continue
                try:
                    ph = P.p_on_time(payload, dict(
                        prompt_tokens=rq["prompt_tokens"], cached_tokens=rq["cached_tokens"],
                        queue_uncached_ahead=ft["queue_uncached_ahead"],
                        queue_decode_ahead=ft["queue_decode_ahead"],
                        t_submit=float(rq["t_submit"]), deadline_abs_s=float(dl)))
                except P.OnTimeInputMissing:
                    n_skip += 1
                    continue
                td_ = o.get("t_delivered")
                on_time = bool(td_ is not None and float(td_) <= float(dl) + 1e-9)
                rows.append(dict(cell=c["cell"], arm=c["arm"], seed=c["seed"], opp=oid,
                                 p_hat=ph, on_time=on_time, warm=bool(ft["warm"]),
                                 error=A_D2_DEV * abs(ph - (1.0 if on_time else 0.0))))
                n_h += 1
            per_cell[c["cell"]] = dict(robot_questions=len(robq), released=len(by_opp),
                                       healthy_scored=n_h, skipped_missing_input=n_skip)
    warm = [r for r in rows if r["warm"]]
    cold = [r for r in rows if not r["warm"]]

    def p90(v):
        if not v:
            return None
        s = sorted(v)
        return round(s[min(int(round(0.9 * (len(s) - 1))), len(s) - 1)], 6)
    res = dict(
        _order="P_hat frozen (082a6e3b) -> population committed (082a6e3b) -> this computation",
        p_hat_version=payload["version"],
        per_cell=per_cell,
        n_overall=len(rows), n_warm=len(warm), n_cold=len(cold),
        thresholds=dict(min_n=MIN_N, min_n_warm=MIN_WARM),
        error_p90_overall=p90([r["error"] for r in rows]),
        error_p90_warm=p90([r["error"] for r in warm]),
        error_p90_cold=p90([r["error"] for r in cold]),
        error_p50_overall=(round(st.median([r["error"] for r in rows]), 6) if rows else None),
        on_time_rate=(round(sum(1 for r in rows if r["on_time"]) / len(rows), 4) if rows else None),
        p_hat_mean=(round(st.fmean(r["p_hat"] for r in rows), 4) if rows else None))
    ok = len(rows) >= MIN_N and len(warm) >= MIN_WARM
    res["margin_cf"] = res["error_p90_overall"] if ok else None
    res["verdict"] = ("SET" if ok else
                      f"NOT SET: n_overall={len(rows)} (need {MIN_N}), n_warm={len(warm)} "
                      f"(need {MIN_WARM}). D169 step 3: do not set, report n.")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=2))
    for k, v in per_cell.items():
        print(f"  {k[:52]:54s} {v}")
    print(f"\nn_overall={res['n_overall']} n_warm={res['n_warm']} n_cold={res['n_cold']}")
    print(f"p90 overall={res['error_p90_overall']} warm={res['error_p90_warm']} "
          f"cold={res['error_p90_cold']}")
    print(f"on_time_rate={res['on_time_rate']} p_hat_mean={res['p_hat_mean']}")
    print(f"VERDICT: {res['verdict']}")
    print(f"MARGIN_CF = {res['margin_cf']}")


if __name__ == "__main__":
    main()
