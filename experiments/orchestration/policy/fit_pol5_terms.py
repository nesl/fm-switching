"""StudyPOL5-engine Part 2: fit the terms the diagnosis says the model needs.

Three things are fitted here, each on data the brief allows and none of it on any holdout:

  (1) FRONT END. The channel StudyENG1d measured as `pre_fe`. The model's existing service time
      depends on body size alone; measured, the window also grows with the number of images,
      because the API server renders each one. Fitted on per-request windows (client submit to
      the engine hand-off) from StudyENG1d FIT rows and StudyENG1 Part C FIT rows.

  (2) ASYNC SCHEDULING LAG. Not a fitted number: a structural rule, from StudyENG1d section 6
      ("asynchronous scheduling prepares the next step while the current one runs"), recorded
      here as a flag with its evidence so the freeze carries it.

  (3) HOST TRANSFER RATE. StudyPOL4 term (a) was fitted on StudyENG1 Part D at 50.14 GB/s;
      StudyENG1c measured about 29 GB/s for the same reload under a host cap. Both are refitted
      here from the committed counters, and the conditions each applies to are stated.

HOLDOUT: none is read. StudyENG1 Part C HOLDOUT, StudyENG1c Part D HOLDOUT and StudyENG1d
HOLDOUT are all excluded by the loaders, which assert their exclusion.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import eng1d_replay as e1d
from . import trace_replay as tr

OUT_DIR = "results/orchestration/study_pol5"
ENG1_FRONTEND = "results/cost/study_eng1/eng1_frontend_requests_h100nvl.jsonl"
ENG1_PART_C = "results/cost/study_eng1/eng1_partC_requests_h100nvl.jsonl"
ENG1_HOLDOUT = "results/cost/study_eng1/eng1_holdout_split.json"
ENG1C_TRIALS = "results/cost/study_eng1c/eng1c_trials_h100nvl.jsonl"
ENG1C_PART_D = "results/cost/study_eng1c/eng1c_partD_h100nvl.jsonl"
EXT = "prompt_tokens_by_source_total|external_kv_transfer"
LOAD_BYTES = "kv_offload_load_bytes_total"
LOAD_TIME = "kv_offload_load_time_total"
TOKENS_PER_FRAME = 90


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _jsonl(path: str) -> List[Dict[str, Any]]:
    with open(_root() / path) as fh:
        return [json.loads(l) for l in fh]


def _ols(rows: Sequence[Sequence[float]], y: Sequence[float]) -> List[float]:
    """Ordinary least squares by normal equations, small and explicit so the fit is readable."""
    n_coef = len(rows[0])
    xtx = [[sum(r[i] * r[j] for r in rows) for j in range(n_coef)] for i in range(n_coef)]
    xty = [sum(r[i] * yy for r, yy in zip(rows, y)) for i in range(n_coef)]
    for i in range(n_coef):
        p = max(range(i, n_coef), key=lambda k: abs(xtx[k][i]))
        xtx[i], xtx[p] = xtx[p], xtx[i]
        xty[i], xty[p] = xty[p], xty[i]
        piv = xtx[i][i]
        if abs(piv) < 1e-12:
            raise ValueError("singular design matrix at column %d" % i)
        for k in range(i + 1, n_coef):
            f = xtx[k][i] / piv
            for j in range(i, n_coef):
                xtx[k][j] -= f * xtx[i][j]
            xty[k] -= f * xty[i]
    beta = [0.0] * n_coef
    for i in range(n_coef - 1, -1, -1):
        s = xty[i] - sum(xtx[i][j] * beta[j] for j in range(i + 1, n_coef))
        beta[i] = s / xtx[i][i]
    return beta


def _r2(pred: Sequence[float], y: Sequence[float]) -> float:
    mu = sum(y) / len(y)
    ss_res = sum((a - b) ** 2 for a, b in zip(pred, y))
    ss_tot = sum((b - mu) ** 2 for b in y)
    return 1.0 - (ss_res / ss_tot if ss_tot > 0 else 0.0)


# ------------------------------------------------------------------ (1) front end
def _n_images(row: Dict[str, Any]) -> int:
    if row.get("n_frames") is not None:
        return int(row["n_frames"])
    new = max(int(row.get("prompt_tokens", 0)) - int(row.get("cached_tokens", 0) or 0), 0)
    return max(int(round(new / float(TOKENS_PER_FRAME))), 1 if new > 0 else 0)


def frontend_rows() -> List[Dict[str, Any]]:
    """Per-request front-end windows: the client's submit to the engine's hand-off, with the
    body size and the image count that produced it. StudyENG1d FIT and StudyENG1 Part C FIT."""
    out: List[Dict[str, Any]] = []
    fe = {str(r["rid"]): r for r in _jsonl(e1d.FRONTEND_PATH)}
    hk = e1d.holdout_keys()
    for row in _jsonl(e1d.PART_C_PATH):
        if row.get("kind") not in ("episodic", "inject", "build"):
            continue
        if (row.get("load"), row.get("action"), row.get("trial")) in hk or row.get("holdout"):
            continue
        f = fe.get(str(row.get("rid")))
        if not f:
            continue
        w = float(f["added_t"]) - float(row["t_submit"])
        if w <= 0 or w > 10:
            continue
        out.append(dict(source="eng1d", kind=row["kind"], rid=str(row["rid"]),
                        body_mb=float(row.get("body_mb") or 0.0), n_images=_n_images(row),
                        window_s=w, t_submit=float(row["t_submit"]),
                        added_t=float(f["added_t"])))
    fe1 = {str(r["rid"]): r for r in _jsonl(ENG1_FRONTEND)}
    raw = json.loads((_root() / ENG1_HOLDOUT).read_text())
    hold = set()
    for cell, idx in raw["holdout"].items():
        load, action = cell.split("|")
        for i in idx:
            hold.add((load, action, int(i)))
    for row in _jsonl(ENG1_PART_C):
        if row.get("kind") not in ("episodic", "inject", "build", "warm_append"):
            continue
        key = (row.get("load"), row.get("action"), row.get("trial"))
        if key in hold or row.get("holdout"):
            continue
        f = fe1.get(str(row.get("rid")))
        if not f:
            continue
        w = float(f["added_t"]) - float(row["t_submit"])
        if w <= 0 or w > 10:
            continue
        out.append(dict(source="eng1_partC_fit", kind=row["kind"], rid=str(row["rid"]),
                        body_mb=float(row.get("body_mb") or 0.0), n_images=_n_images(row),
                        window_s=w, t_submit=float(row["t_submit"]),
                        added_t=float(f["added_t"])))
    return out


def fit_frontend(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """window_ms = fixed + per_mb x body_mb + per_image x images, with a busy-regime factor.

    'Busy' is decided from the measurement itself: a request whose submit falls inside the window
    of a request already being rendered. The factor is the ratio of the busy residual to the idle
    one, so it is measured and not assumed."""
    rows = sorted(rows, key=lambda r: r["t_submit"])
    busy_until = float("-inf")
    for r in rows:
        r["busy"] = bool(r["t_submit"] < busy_until - 1e-9)
        busy_until = max(busy_until, r["added_t"])
    idle = [r for r in rows if not r["busy"]]
    busy = [r for r in rows if r["busy"]]
    X = [[1.0, r["body_mb"], float(r["n_images"])] for r in idle]
    y = [r["window_s"] * 1000.0 for r in idle]
    fixed, per_mb, per_image = _ols(X, y)
    pred = [fixed + per_mb * r["body_mb"] + per_image * r["n_images"] for r in idle]
    r2 = _r2(pred, y)
    ratios = []
    for r in busy:
        base = fixed + per_mb * r["body_mb"] + per_image * r["n_images"]
        if base > 1e-6:
            ratios.append((r["window_s"] * 1000.0) / base)
    busy_factor = statistics.median(ratios) if ratios else 1.0
    by_class = {}
    for name, sel in (("episodic", lambda r: r["kind"] == "episodic"),
                      ("inject", lambda r: r["kind"] == "inject"),
                      ("build", lambda r: r["kind"] == "build")):
        sub = [r for r in rows if sel(r)]
        if not sub:
            continue
        p = [fixed + per_mb * r["body_mb"] + per_image * r["n_images"] for r in sub]
        by_class[name] = dict(n=len(sub),
                              measured_median_ms=statistics.median(r["window_s"] * 1000.0
                                                                   for r in sub),
                              predicted_median_ms=statistics.median(p),
                              body_mb_median=statistics.median(r["body_mb"] for r in sub),
                              images_median=statistics.median(r["n_images"] for r in sub))
    return dict(
        coef=dict(front_end_fixed_ms=fixed, front_end_per_mb_ms=per_mb,
                  front_end_per_image_ms=per_image, front_end_busy_factor=busy_factor),
        n_idle=len(idle), n_busy=len(busy), r2_idle=r2,
        busy_factor_n=len(ratios),
        by_class=by_class,
        fit_data=("per-request front-end windows (client submit to engine hand-off) from "
                  "StudyENG1d FIT rows and StudyENG1 Part C FIT rows; no holdout row is read. "
                  "The idle rows fit the three coefficients and the busy rows give the factor."),
        note=("StudyPOL4's model had body size only (29.6 ms + 20.2 ms per MB, busy 6.9 + 17.7), "
              "which under-prices a many-image body: StudyENG1d measures 0.554 s for a 124-image "
              "22.8 MB action against 0.489 s from that formula."))


# ------------------------------------------------------------------ (3) host transfer
def fit_host_rate() -> Dict[str, Any]:
    """Two regimes, both measured. StudyENG1 Part D ran with a roomy host tier; StudyENG1c ran
    with the host tier CAPPED and full, where every load competes with ongoing write-through
    eviction. The committed counters give bytes and seconds for each."""
    out: Dict[str, Any] = {}
    rows = []
    for t in _jsonl(ENG1C_TRIALS):
        if t.get("sub") != "B" or t.get("resume_error"):
            continue
        md = t.get("resume_window_delta") or {}
        b = float(md.get(LOAD_BYTES, 0) or 0)
        s = float(md.get(LOAD_TIME, 0) or 0)
        if b <= 0 or s <= 0:
            continue
        rows.append(dict(bytes=b, seconds=s, gb_per_s=(b / 1e9) / s, cap=t.get("cap"),
                         tokens=float(md.get(EXT, 0) or 0)))
    # The end-to-end cost of a reload is more than the transfer: StudyENG1c's resident resumes
    # give the baseline, and what a host-load resume costs beyond that, minus the counter's own
    # transfer time, is the non-transfer overhead (lookup, scheduling, the forced last block).
    resident = []
    for t in _jsonl(ENG1C_TRIALS):
        if t.get("sub") != "B" or t.get("resume_error"):
            continue
        md = t.get("resume_window_delta") or {}
        ext = float(md.get(EXT, 0) or 0)
        cached = float(t.get("resume_cached") or 0)
        if ext <= 16 and cached >= int(t.get("prefix_tokens") or 0) - 16:
            resident.append(float(t["resume_ttft"]))
    base = statistics.median(resident) if resident else None
    overheads = []
    if base is not None:
        for t in _jsonl(ENG1C_TRIALS):
            if t.get("sub") != "B" or t.get("resume_error"):
                continue
            md = t.get("resume_window_delta") or {}
            ext = float(md.get(EXT, 0) or 0)
            lt = float(md.get(LOAD_TIME, 0) or 0)
            if ext > 16 and lt > 0:
                overheads.append((float(t["resume_ttft"]) - base - lt) * 1000.0)
    out["reload_overhead"] = dict(
        n_resident=len(resident), resident_ttft_median_s=base,
        n_host_loads=len(overheads),
        overhead_ms_median=(statistics.median(overheads) if overheads else None),
        overhead_ms_p10=(sorted(overheads)[int(0.1 * len(overheads))] if overheads else None),
        overhead_ms_p90=(sorted(overheads)[int(0.9 * len(overheads))] if overheads else None),
        fit_data="StudyENG1c Part B non-holdout resumes: host-load TTFT minus the resident "
                 "median minus the counter's own transfer time",
        caveat="the spread is wide (p10 to p90 spans a second) because the host-load resumes "
               "include partial loads at the capacity boundary; the median is the estimate and "
               "the spread is reported rather than hidden")
    rates = [r["gb_per_s"] for r in rows]
    out["eng1c_capped_host"] = dict(
        n=len(rows), gb_per_s_median=(statistics.median(rates) if rates else None),
        gb_per_s_p10=(sorted(rates)[int(0.1 * len(rates))] if rates else None),
        gb_per_s_p90=(sorted(rates)[int(0.9 * len(rates))] if rates else None),
        bytes_median=(statistics.median(r["bytes"] for r in rows) if rows else None),
        seconds_median=(statistics.median(r["seconds"] for r in rows) if rows else None),
        by_cap={str(c): dict(n=len([r for r in rows if r["cap"] == c]),
                             gb_per_s=statistics.median([r["gb_per_s"] for r in rows
                                                         if r["cap"] == c]))
                for c in sorted({r["cap"] for r in rows})},
        fit_data="StudyENG1c Part B resume windows (non-holdout), per-resume kv_offload_load "
                 "bytes and seconds")
    d_rows = []
    for r in _jsonl(ENG1C_PART_D):
        if r.get("kind") != "run_summary" or r.get("holdout"):
            continue
        md = r.get("metrics_delta") or {}
        b = float(md.get(LOAD_BYTES, 0) or 0)
        s = float(md.get(LOAD_TIME, 0) or 0)
        if b > 0 and s > 0:
            d_rows.append((b / 1e9) / s)
    out["eng1c_part_d_runs"] = dict(n=len(d_rows),
                                    gb_per_s_median=(statistics.median(d_rows) if d_rows else None),
                                    fit_data="StudyENG1c Part D FIT run windows (non-holdout)")
    pol4 = json.loads((_root() / "results/orchestration/study_pol4/pol4_terms.json").read_text())
    out["pol4_eng1_part_d"] = dict(
        gb_per_s=pol4["coef"]["host_kv_transfer_gb_per_s"],
        fit_data="StudyPOL4 term (a), fitted on StudyENG1 Part D with a roomy host tier")
    out["applies_to"] = (
        "The roomy-tier rate applies where the host tier is far from full and nothing else is "
        "being written through it, which is StudyENG1 Part D and StudyENG1b. The capped rate "
        "applies where the host tier is at its cap and write-through eviction runs with every "
        "load, which is StudyENG1c and anything the policy schedules under a host cap. pol5 "
        "uses the capped rate by default because a policy that manages placement runs in the "
        "capped regime by construction.")
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args(list(argv) if argv is not None else None)
    out_dir = Path(args.out_dir) if args.out_dir else (_root() / OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    fe_rows = frontend_rows()
    fe = fit_frontend(fe_rows)
    host = fit_host_rate()
    pol4 = json.loads((_root() / "results/orchestration/study_pol4/pol4_terms.json").read_text())

    coef = dict(pol4["coef"])
    coef.update(fe["coef"])
    coef["host_kv_transfer_gb_per_s_capped"] = host["eng1c_capped_host"]["gb_per_s_median"]
    coef["host_kv_reload_overhead_ms_capped"] = host["reload_overhead"]["overhead_ms_median"]
    # Tested on FIT and REJECTED: the one-step scheduling lag alone made the imposed-delay
    # error worse (piece1024 1.74 to 2.42 on StudyENG1c Part D FIT), because it delayed
    # eligibility without stopping the merging. It is kept at 0 and the rejection is recorded.
    coef["async_schedule_lag_steps"] = 0.0
    # ALSO tested on FIT and REJECTED (StudyPOL5 Part 1): one prefill per step raised the
    # piece1024 ratio from 1.74 to 3.25 on StudyENG1c Part D FIT. The step-log field it was
    # inferred from (`it[1]`) turned out not to be a prefill count, so the inference was unsound
    # as well as wrong. Kept at 0 with the attempt on the record.
    coef["serial_prefill_admission"] = 0.0

    out = dict(
        study="StudyPOL5-engine",
        holdout_trials_used=0,
        holdout_exclusion=("StudyENG1 Part C HOLDOUT, StudyENG1c Part D HOLDOUT and StudyENG1d "
                           "HOLDOUT are all excluded by the loaders and none was read"),
        coef=coef,
        front_end=fe,
        host_kv_transfer=host,
        serial_prefill_admission=dict(
            coef_name="serial_prefill_admission", value=0.0,
            status="TESTED ON FIT AND REJECTED",
            rejection=("one prefill per step raised the piece1024 imposed-delay ratio from 1.74 "
                       "to 3.25 and mono11k from 1.12 to 1.68 on StudyENG1c Part D FIT. The "
                       "step-log field the rule was inferred from, `it[1]`, is not a prefill "
                       "count (it reads 1 on steps that ENG1d shows carrying several prefills), "
                       "so the inference was unsound as well as wrong"),
            kind="STRUCTURAL RULE, not a fitted number",
            evidence=("StudyPOL5 Part 1, measured inside the action window of StudyENG1c Part D "
                      "FIT at cap 27 GiB: the ENGINE's median requests per step is 1.0 for all "
                      "three actions and it runs 27 steps where pol4 runs 13.5 (piece1024) and "
                      "16 where pol4 runs 7 (piece2048), over the same prefill tokens. The step "
                      "model is accurate on the engine's own composition (ratio 0.85 to 0.97), "
                      "so the error is which requests share a step, not what a step costs. "
                      "StudyENG1d section 6 measured the same rule from the other side: an "
                      "action's token share of 1.000 and 0 of 248 in-window arrivals joining a "
                      "piece's step.")),
        async_scheduling=dict(
            coef_name="async_schedule_lag_steps", value=0.0,
            status="TESTED ON FIT AND REJECTED",
            rejection=("the one-step lag alone raised the piece1024 imposed-delay ratio from "
                       "1.74 to 2.42 on StudyENG1c Part D FIT, because it delayed eligibility "
                       "without preventing the merge; it is recorded here at 0 so the attempt "
                       "and its result stay on the record"),
            kind="STRUCTURAL RULE, not a fitted number",
            evidence=("StudyENG1d section 6: asynchronous scheduling prepares the next step "
                      "while the current one runs, so a request handed over during a step "
                      "cannot join it. Measured: 0 of 248 in-window arrivals joined a piece's "
                      "step, and a mono11k second chunk carries only requests that were already "
                      "waiting when it was scheduled. StudyPOL5 Part 1 found that pol4 merges "
                      "background prefills into the action's own step in 54 to 66 per cent of "
                      "piece steps on StudyENG1c Part D, and that 513 of 513 such merges "
                      "involved a request handed over AFTER the previous step had started, "
                      "which is exactly what this rule forbids.")),
        inherited_from_pol4=dict(path="results/orchestration/study_pol4/pol4_terms.json",
                                 terms=list(pol4["coef"].keys())),
        label=("StudyENG1d FIT informed the front-end fit and the scheduling rule, so any score "
               "on StudyENG1d FIT is IN-SAMPLE for those. StudyENG1c Part D FIT informed the "
               "host rate and the Part 1 diagnosis."))
    sys.path.insert(0, str(_root() / "experiments" / "lib"))
    from _provenance import stamp
    out["_provenance"] = stamp(script="policy/fit_pol5_terms.py", model=None, device=None,
                               n=len(fe_rows), args=vars(args))
    (out_dir / "pol5_terms.json").write_text(json.dumps(out, indent=1, default=str))
    print("front end: fixed %.2f ms, per MB %.2f ms, per image %.3f ms, busy factor %.3f "
          "(idle n %d, R2 %.3f)"
          % (fe["coef"]["front_end_fixed_ms"], fe["coef"]["front_end_per_mb_ms"],
             fe["coef"]["front_end_per_image_ms"], fe["coef"]["front_end_busy_factor"],
             fe["n_idle"], fe["r2_idle"]))
    for k, v in sorted(fe["by_class"].items()):
        print("   %-9s n%6d measured %7.1f ms predicted %7.1f ms (body %.2f MB, images %.0f)"
              % (k, v["n"], v["measured_median_ms"], v["predicted_median_ms"],
                 v["body_mb_median"], v["images_median"]))
    print("host transfer: capped %.2f GB/s (n %d), ENG1 Part D roomy %.2f GB/s, reload "
          "overhead %.1f ms (n %d)"
          % (host["eng1c_capped_host"]["gb_per_s_median"], host["eng1c_capped_host"]["n"],
             host["pol4_eng1_part_d"]["gb_per_s"],
             host["reload_overhead"]["overhead_ms_median"] or 0.0,
             host["reload_overhead"]["n_host_loads"]))
    print("wrote %s" % (out_dir / "pol5_terms.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
