#!/usr/bin/env python3
"""StudyE9b-dense control (a) — end-to-end reproduction of StudyE9 and StudyE12.

On integer-t rows only, with d = ceil(latency) and 1-s cadences, the dense engine must reproduce
the committed numbers of both prior studies. Two input variants, fixed before any computation:

  a1  input = StudyD14's own trace (the input StudyE9 and StudyE12 consumed) -> must be EXACT.
  a2  input = StudyD14b's integer-t rows -> bounded below by a 1-ulp input difference in
      score = log P(Yes) on 21 of 42,640 rows (p_yes is bit-identical on all 42,640).

CPU ONLY: no GPU, no model server, no inference.
"""
import json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/dashcam"))
import study_e9_episodes as E9  # noqa: E402
import study_e9b_dense as B  # noqa: E402
import study_e9b_admission as A  # noqa: E402

OUT = ROOT / "results/dashcam/study_e9b"
E9R = json.loads((ROOT / "results/dashcam/study_e9/e9_results.json").read_text())
E12R = json.loads((ROOT / "results/dashcam/study_e12/e12_results.json").read_text())
ARMS = [("4BI", 1), ("32BI", 1), ("32BI", 3)]
P = E9.PRIMARY


def study1_check(use_d14):
    ctx = B.build(step=1.0, horizons=E9.HORIZONS, integer_only=not use_d14,
                  ceil_delivery=True, use_d14=use_d14)
    eng, meta, clips, tau, fold = ctx["eng"], ctx["meta"], ctx["clips"], ctx["tau"], ctx["fold"]
    out = dict(ap_comparisons=0, worst_ap=0.0, worst_ci=0.0, count_comparisons=0, mismatches=[])

    def cmp_ap(ap, ref):
        for h in E9.HORIZONS:
            out["ap_comparisons"] += 1
            out["worst_ap"] = max(out["worst_ap"], abs(ap[h]["ap"] - ref[str(h)]["ap"]))
            out["worst_ci"] = max(out["worst_ci"],
                                  abs(ap[h]["ci"][0] - ref[str(h)]["ci"][0]),
                                  abs(ap[h]["ci"][1] - ref[str(h)]["ci"][1]))

    for st in ("zero", "measured@25", "measured@75"):
        seen_all, mdev, Ddev, _L = B.dev_seen_all(ctx, st)
        for far in E9.ALARM_FPR:
            ap, _b = eng.full(seen_all)
            cmp_ap(ap, E9R["baselines"][f"device-only|{st}|far{int(far*100)}"]["ap"])
        for arm in ARMS[1:]:
            _d, Lc = B.latencies(st, *arm)
            Dc = B.steps_ceil_second(Lc, 1.0)
            streams = {c: B.held_stream(ctx["arrs"][arm][c], meta[c]["G"], 1, Dc) for c in clips}
            ap, _b = eng.full(streams)
            for far in E9.ALARM_FPR:
                cmp_ap(ap, E9R["baselines"][(f"always-cloud/{arm[0]}_N{arm[1]}|{st}|"
                                             f"far{int(far*100)}")]["ap"])
    for st in ("zero", "measured@25", "measured@75"):
        for rmodel, rn in [("32BI", 1), ("32BI", 3), ("4BI", 1)]:
            pol = "escalation-32B" if rmodel == "32BI" else "escalation-4B"
            for far in E9.ALARM_FPR:
                for trig in E9.TRIG_RATE:
                    r = B.run_escalation(ctx, rmodel, rn, st, 1.0, far, trig, P["k"], P["q"],
                                         P["lmax"], P["c"])
                    key = (f"{pol}|{rmodel}_N{rn}|{st}|far{int(far*100)}|trig{int(trig*100)}|"
                           f"q{int(P['q']*100)}|k{P['k']}|L{P['lmax']}|c{P['c']}")
                    ref = E9R["cells"][key]
                    es = B.episode_stats(ctx, r["eps"], r["inv"], rmodel, rn)
                    al = B.alarm_stats(ctx, r["alarm_i"], r["nev"])
                    for lab in ("positive", "negative"):
                        out["count_comparisons"] += 3
                        if (es[lab]["episodes"] != ref["episodes"][lab]["episodes"]
                                or es[lab]["invocations"] != ref["episodes"][lab]["invocations"]
                                or es[lab]["outcomes"] != ref["episodes"][lab]["outcomes"]):
                            out["mismatches"].append(f"{key}|{lab}")
                    out["count_comparisons"] += 3
                    if (al["n_positive_alarmed"] != ref["alarms"]["n_positive_alarmed"]
                            or al["false_alarm_events_negative"] != ref["alarms"]["false_alarm_events_negative"]
                            or es["false_dismissals_positive_before_event"] != ref["episodes"]["false_dismissals_positive_before_event"]):
                        out["mismatches"].append(f"{key}|alarms")
                    ap, _b = eng.full(r["streams"])
                    cmp_ap(ap, ref["ap"])
    return out


def study2_check(use_d14):
    res = A.main(step=1.0, horizons=E9.HORIZONS, cadence=1.0, integer_only=not use_d14,
                 ceil_delivery=True, use_d14=use_d14,
                 outfile=f"e9b_control_a_study2_{'d14' if use_d14 else 'd14b'}.json")
    out = dict(cells_compared=0, worst_ap=0.0, worst_ci=0.0, worst_scalar_rel=0.0, mismatches=[])
    for k, d in res["cells"].items():
        if k not in E12R["cells"]:
            out["mismatches"].append(f"MISSING {k}")
            continue
        ref = E12R["cells"][k]
        out["cells_compared"] += 1
        for h in E9.HORIZONS:
            out["worst_ap"] = max(out["worst_ap"], abs(d["ap"][h]["ap"] - ref["ap"][str(h)]["ap"]))
            if d["ap"][h]["ci"] and ref["ap"][str(h)]["ci"]:
                out["worst_ci"] = max(out["worst_ci"],
                                      abs(d["ap"][h]["ci"][0] - ref["ap"][str(h)]["ci"][0]),
                                      abs(d["ap"][h]["ci"][1] - ref["ap"][str(h)]["ci"][1]))
        for f in ("invocations", "admitted", "episodes", "fraction_positive_alarmed",
                  "false_alarm_events_negative", "false_alarms_per_clip_hour",
                  "gpu_seconds_per_clip_hour", "realized_admitted_fraction"):
            a, b = d.get(f), ref.get(f)
            if a is None or b is None:
                if a != b:
                    out["mismatches"].append(f"{k}|{f}|{a}|{b}")
                continue
            den = max(abs(float(b)), 1e-12)
            rel = abs(float(a) - float(b)) / den
            out["worst_scalar_rel"] = max(out["worst_scalar_rel"], rel)
            if rel > 1e-9:
                out["mismatches"].append(f"{k}|{f}|{a}|{b}")
    out["n_cells_committed"] = len(E12R["cells"])
    out["diagnostics_match"] = {}
    for kb, dg in res["diagnostics"].items():
        rg = E12R["diagnostics"].get(kb)
        if rg is None:
            continue
        ok = dg["n_triggers"] == rg["n_triggers"]
        for f in ("fold0", "fold1"):
            for fld in ("n_train_triggers", "auroc_benefit_gt0", "work_r2_train"):
                a, b = dg["folds"][f][fld], rg["folds"][f][fld]
                ok = ok and (a == b if not isinstance(a, float)
                             else abs(a - b) < 1e-12)
        out["diagnostics_match"][kb] = bool(ok)
    return out


def main():
    rep = dict(label="StudyE9b-dense control (a): end-to-end reproduction of StudyE9 and StudyE12 "
                     "on integer-t rows with d = ceil(latency) and 1-s cadences. CPU only.",
               input_check=dict(), study1={}, study2={})
    for tag, use_d14 in (("a1_input_StudyD14", True), ("a2_input_StudyD14b_integer_rows", False)):
        print("=== Study 1", tag, flush=True)
        rep["study1"][tag] = study1_check(use_d14)
        print(json.dumps(rep["study1"][tag])[:400], flush=True)
    for tag, use_d14 in (("a1_input_StudyD14", True), ("a2_input_StudyD14b_integer_rows", False)):
        print("=== Study 2", tag, flush=True)
        rep["study2"][tag] = study2_check(use_d14)
        print(json.dumps(rep["study2"][tag])[:600], flush=True)
    rep["verdict"] = dict(
        study1_a1_exact=bool(rep["study1"]["a1_input_StudyD14"]["worst_ap"] == 0.0
                             and rep["study1"]["a1_input_StudyD14"]["worst_ci"] == 0.0
                             and not rep["study1"]["a1_input_StudyD14"]["mismatches"]),
        study2_a1_exact=bool(rep["study2"]["a1_input_StudyD14"]["worst_ap"] == 0.0
                             and rep["study2"]["a1_input_StudyD14"]["worst_ci"] == 0.0
                             and not rep["study2"]["a1_input_StudyD14"]["mismatches"]))
    (OUT / "e9b_control_a.json").write_text(json.dumps(rep, indent=1, default=float))
    print(json.dumps(rep["verdict"]))


if __name__ == "__main__":
    main()
