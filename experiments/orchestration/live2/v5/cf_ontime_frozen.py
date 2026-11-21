#!/usr/bin/env python3
"""THE FROZEN ON-TIME MODEL, `P_hat`, that D157 (2) makes MARGIN_CF's definition depend on.
CPU only. No GPU, no engine, no model server, no live run.

    python3 -I experiments/orchestration/live2/v5/cf_ontime_frozen.py --freeze
    python3 -I experiments/orchestration/live2/v5/cf_ontime_frozen.py --verify
    python3 -I experiments/orchestration/live2/v5/cf_ontime_frozen.py --evaluate <cell_dir>

WHAT D157 (2) RULED, and what it makes this file.

    population = every robot question RELEASED in the 4 EP-G WARM-ALL held-out cells (upload-pf),
                 and no other cells, never v5-rules and never a v5 cell
    per question, error = a_D2_DEV (0.250) x | P_hat(on time) - 1[actually on time] |
    MARGIN_CF   = the p90 of that error, set ONCE, frozen, identical in every v5 cell

`P_hat` is this module. D157 (2) requires it **frozen and committed (hash) before those cells are
scored**, and if it is not frozen when they land, the margin waits. So this file exists to be
unchangeable, not to be good: its whole job is that a later scoring pass can PROVE which version it
used.

HOW THE FREEZE IS MADE CHECKABLE, and why each piece is in the hash.

  * The artefact `results/orchestration/live2/v5/cf_ontime_model_frozen.json` carries EVERY number
    the prediction consumes: the two coefficient triples, the 1,001-point residual quantile grid,
    the link term, and the derived safety factor. Nothing is recomputed at call time and nothing is
    read from another file at call time.
  * `payload_sha256` is a content hash over the canonical JSON of exactly that payload. It covers
    the numbers.
  * `code_sha256` is the hash of THIS FILE, because the prediction depends on the arithmetic as
    much as on the coefficients. `load()` verifies BOTH and RAISES `FrozenModelTampered` on either.
    Editing this file therefore breaks the freeze loudly, which is the intended behaviour: a
    re-freeze must be a deliberate, visible act.
  * The prediction here is SELF-CONTAINED: it does not call `cf_cost`. That is deliberate. The
    planner's live path stays in `cf_cost`, and if the two ever drift, `--verify` reports the drift
    instead of the frozen number silently following a later edit.

THE REGISTER OF `P_hat`, which the margin's reader must carry.
`P_hat` is evaluated POST HOC, from the cell's own request log, so its overlap counts are the
overlaps the request ACTUALLY experienced. That is the same definition `cost_model_gate.features`
fitted on, so it is the right thing for a predicted-versus-actual error. It is NOT the planner's
live error: at decision time the planner has a forecast of load, not the realised overlaps. So
**MARGIN_CF as D157 (2) defines it measures the cost model's error given perfect knowledge of
concurrency, which is a LOWER BOUND on the planner's own error.** That is a property of the ruling,
not a defect of this file, and it is stated here so nobody has to rediscover it from the code. The
WARM-ALL cells carry no planner, so no live predicted probability exists in them to use instead.

WHAT IT NEEDS PER QUESTION (one line, as asked):
`prompt_tokens`, `cached_tokens`, `overlap_ft`, `overlap_decode`, `t_submit`, `deadline_abs_s`
for the question's own cloud request, where the two overlap counts are derived from the cell's
FULL request log (every other request's `t_submit`, `t_first_token`, `t_done`), and
`deadline_abs_s = t_opportunity + deadline_s` from the recall outcome.

A MISSING INPUT RAISES. `OnTimeInputMissing`, never a default. A `cached_tokens` of None is a
missing input and not a zero: `backend.cached_tokens_of` returns None rather than 0 precisely
because a zero "would be read as a confirmed cold path", and a model that silently read None as 0
would price a warm request as cold and understate the margin.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
for _p in (str(HERE), str(REPO / "experiments/orchestration/live2"),
           str(REPO / "experiments/lib")):
    if _p not in sys.path:
        sys.path.append(_p)

FROZEN_MODEL_VERSION = "cf-ontime-1.0"
ARTEFACT = REPO / "results/orchestration/live2/v5/cf_ontime_model_frozen.json"

# D157 (2): the accuracy factor in the error formula, the committed DEV cloud-D2 figure. Declared
# here so the error formula is evaluable from this file alone, and cross-checked against the
# committed table at freeze time.
A_D2_DEV = 0.250

REQUIRED_INPUTS: Tuple[str, ...] = ("prompt_tokens", "cached_tokens", "overlap_ft",
                                    "overlap_decode", "t_submit", "deadline_abs_s")

# The population guard (D157 (2)). A cell is in the margin's population only if its own
# `run_meta.json::label` says so. These are the substrings looked for; if the EP-G WARM-ALL
# held-out cells label themselves differently, `margin_from_cells` RAISES and names exactly what it
# looked for, rather than computing a margin on the wrong cells.
POPULATION_ARM = "warm-all-lru"
POPULATION_LABEL_REQUIRED: Tuple[str, ...] = ("EP-G", "upload-pf")
POPULATION_LABEL_FORBIDDEN: Tuple[str, ...] = ("dashcam-1f", "upload-30s", "v5-rules")

OVERLAP_DEFINITION = (
    "cost_model_gate.features, unchanged: for a request with first-token window [t_submit, "
    "t_first_token) and decode window [t_first_token, t_done), the overlap count is the number of "
    "OTHER requests in the same cell whose corresponding interval intersects it. Only requests "
    "with t_submit, t_first_token, t_done and prompt_tokens all present enter the count, which is "
    "the same filter the gate fitted under.")

FORMULA = (
    "first_token = ft_intercept + ft_per_uncached_token x max(prompt_tokens - cached_tokens, 0) "
    "+ ft_per_overlap x overlap_ft; decode = dec_intercept + dec_per_overlap x overlap_decode; "
    "engine_service = first_token + decode; slack = deadline_abs_s - t_submit - link_rtt_s; "
    "P_hat = F_ratio(slack / engine_service), F_ratio the empirical CDF of actual-over-predicted "
    "engine service on the committed held-out-by-arm requests, linearly interpolated, 0 below its "
    "support and 1 above it.")


class OnTimeInputMissing(RuntimeError):
    """A per-question input was absent or None. Raised, never defaulted (D157 (2), item 4)."""


class FrozenModelTampered(RuntimeError):
    """The artefact's payload hash or this file's code hash does not match the freeze."""


class MarginPopulationRefused(RuntimeError):
    """A margin was asked for on cells outside D157 (2)'s declared population."""


# ---------------------------------------------------------------------------
# hashing


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def payload_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def code_hash(path: Optional[Path] = None) -> str:
    return hashlib.sha256((path or Path(__file__).resolve()).read_bytes()).hexdigest()


def _file_sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# the freeze


def build_payload() -> Dict[str, Any]:
    """Collect every number the prediction consumes into one flat, self-contained payload."""
    import cf_cost as CC                                                       # noqa: PLC0415
    import cf_margin as CM                                                     # noqa: PLC0415
    import value_readers as VR                                                 # noqa: PLC0415
    model = CC.load_gate_model()
    res = CC.load_residuals()
    sf = CM.safety_factor(res)
    table = VR.load_dev_table()
    if abs(float(table["cloud_D2"]) - A_D2_DEV) > 1e-9:
        raise RuntimeError(
            "D157 (2)'s error formula uses a_D2_DEV = %.3f and the committed DEV table now says "
            "%.6f. The formula's constant and the table have diverged; this is a ruling-level "
            "disagreement and the freeze refuses rather than choosing one."
            % (A_D2_DEV, float(table["cloud_D2"])))
    return {
        "version": FROZEN_MODEL_VERSION,
        "formula": FORMULA,
        "required_inputs": list(REQUIRED_INPUTS),
        "overlap_definition": OVERLAP_DEFINITION,
        "a_D2_DEV": A_D2_DEV,
        "coefficients": {
            "ft_intercept": float(model["first_token"]["intercept"]),
            "ft_per_uncached_token": float(model["first_token"]["per_uncached_token"]),
            "ft_per_overlap": float(model["first_token"]["per_overlap"]),
            "dec_intercept": float(model["decode"]["intercept"]),
            "dec_per_overlap": float(model["decode"]["per_overlap"]),
        },
        "link_rtt_s": float(CC.LINK_RTT_S),
        "safety_factor": float(sf["safety_factor"]),
        "safety_factor_note": ("the latest-safe-start factor, the p90 of the same residual ratio, "
                              "floored at 1.0. It is NOT used by P_hat and is frozen here because "
                              "it is a derived factor of the same model and the coordinator asked "
                              "for it to be fixed in the file rather than recomputed"),
        "ratio_cdf": {"q": list(res["ratio_quantiles"]["q"]),
                      "value": [float(v) for v in res["ratio_quantiles"]["value"]]},
        "sources": {
            "gate_model": {"file": "results/orchestration/live2/frozen_test/cost_model_gate.json",
                           "sha256": _file_sha256(CC.GATE_JSON), "split": model["_split"],
                           "fit_on": model["_fit_on"], "test_on": model["_test_on"]},
            "residuals": {"file": "results/orchestration/live2/v5/cf_service_residuals.json",
                          "sha256": _file_sha256(CC.RESIDUALS_JSON),
                          "n_held_out": res["n_held_out"],
                          "warm_rows_held_out": res["warm_rows_held_out"]},
            "accuracy_table": {"file": "results/orchestration/live2/lh_req/lh_req_quality.json",
                               "cloud_D2_DEV": float(table["cloud_D2"])},
        },
    }


def freeze(out: Path = ARTEFACT) -> Dict[str, Any]:
    payload = build_payload()
    art = {
        "_what": ("the FROZEN on-time model P_hat that D157 (2) makes MARGIN_CF depend on. Every "
                  "number the prediction consumes is in `payload`; nothing is recomputed at call "
                  "time"),
        "_rule": ("D157 (2): population = every robot question released in the 4 EP-G WARM-ALL "
                  "held-out cells (upload-pf) and no other cells; per question error = 0.250 x "
                  "|P_hat - 1[on time]|; MARGIN_CF = the p90 of that error, set once, frozen"),
        "_register": ("P_hat is evaluated POST HOC from the cell's own request log, so its overlap "
                      "counts are the overlaps actually experienced. It measures the cost model's "
                      "error given perfect knowledge of concurrency, which is a LOWER BOUND on the "
                      "planner's live error. The WARM-ALL cells carry no planner, so no live "
                      "predicted probability exists in them to use instead"),
        "_gate_status": ("the D151 (6) gate still FAILS (decode over-predicts by 25 to 32 percent, "
                         "warm confounded with arm). D157 (2) defines the margin's units without "
                         "waiting for it; the value still may not be set from a failing gate's "
                         "cells other than the four it names"),
        "payload": payload,
        "payload_sha256": payload_hash(payload),
        "code_sha256": code_hash(),
        "code_file": "experiments/orchestration/live2/v5/cf_ontime_frozen.py",
        "population_guard": {"arm": POPULATION_ARM,
                             "label_must_contain": list(POPULATION_LABEL_REQUIRED),
                             "label_must_not_contain": list(POPULATION_LABEL_FORBIDDEN),
                             "checked_in": "run_meta.json::label and cell.json::arm",
                             "on_mismatch": "MarginPopulationRefused, naming what was looked for"},
    }
    try:
        from _provenance import stamp                                          # noqa: PLC0415
        art["_provenance"] = stamp(script="cf_ontime_frozen.py",
                                   model="n/a (policy design, no model)", device="cpu",
                                   n=len(payload["ratio_cdf"]["q"]), args=None)
    except Exception:                                                          # noqa: BLE001
        pass
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(art, indent=1) + "\n")
    return art


def load(path: Path = ARTEFACT, verify: bool = True) -> Dict[str, Any]:
    """Load the frozen artefact, verifying BOTH hashes. Raises `FrozenModelTampered` on either."""
    if not path.exists():
        raise FileNotFoundError("the frozen on-time model is missing: %s. Build it with "
                                "`cf_ontime_frozen.py --freeze`." % path)
    art = json.loads(path.read_text())
    if verify:
        got = payload_hash(art["payload"])
        if got != art.get("payload_sha256"):
            raise FrozenModelTampered(
                "payload hash mismatch: artefact says %s, content hashes to %s. The frozen "
                "numbers have been changed since the freeze."
                % (art.get("payload_sha256"), got))
        cg = code_hash()
        if cg != art.get("code_sha256"):
            raise FrozenModelTampered(
                "code hash mismatch: artefact was frozen against %s and this file hashes to %s. "
                "P_hat's arithmetic has changed since the freeze; re-freezing is a deliberate act "
                "and must be recorded, so this refuses rather than predicting."
                % (art.get("code_sha256"), cg))
    return art


# ---------------------------------------------------------------------------
# the prediction, self-contained


def _cdf(payload: Dict[str, Any], ratio: float) -> float:
    vals = payload["ratio_cdf"]["value"]
    qs = payload["ratio_cdf"]["q"]
    if ratio <= vals[0]:
        return 0.0
    if ratio >= vals[-1]:
        return 1.0
    i = bisect.bisect_right(vals, ratio) - 1
    i = min(max(i, 0), len(vals) - 2)
    v0, v1 = vals[i], vals[i + 1]
    q0, q1 = qs[i], qs[i + 1]
    if v1 <= v0:
        return float(q1)
    return float(q0 + (q1 - q0) * (ratio - v0) / (v1 - v0))


def _need(row: Dict[str, Any], key: str, where: str) -> float:
    if key not in row:
        raise OnTimeInputMissing("%s: input %r is absent. P_hat refuses rather than defaulting "
                                 "(D157 (2) item 4). Required inputs: %s"
                                 % (where, key, ", ".join(REQUIRED_INPUTS)))
    v = row[key]
    if v is None:
        raise OnTimeInputMissing(
            "%s: input %r is None. A None is a MISSING input and not a zero: "
            "`backend.cached_tokens_of` returns None rather than 0 so that a zero is never read as "
            "a confirmed cold path, and reading it as 0 here would price a warm request as cold "
            "and understate the margin." % (where, key))
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise OnTimeInputMissing("%s: input %r has type %s, which is not a number. P_hat refuses "
                                 "a coerced input." % (where, key, type(v).__name__))
    if isinstance(v, float) and math.isnan(v):
        raise OnTimeInputMissing("%s: input %r is NaN." % (where, key))
    return float(v)


def p_hat(art: Dict[str, Any], row: Dict[str, Any], where: str = "P_hat") -> Dict[str, Any]:
    """P(on time) for ONE robot question, from the frozen payload and nothing else.

    `row` must carry every name in `REQUIRED_INPUTS`. Anything absent, None, non-numeric or NaN
    raises `OnTimeInputMissing`.
    """
    p = art["payload"]
    c = p["coefficients"]
    prompt = _need(row, "prompt_tokens", where)
    cached = _need(row, "cached_tokens", where)
    ov_ft = _need(row, "overlap_ft", where)
    ov_dec = _need(row, "overlap_decode", where)
    t_submit = _need(row, "t_submit", where)
    deadline = _need(row, "deadline_abs_s", where)
    unc = max(prompt - cached, 0.0)
    ft = max(c["ft_intercept"] + c["ft_per_uncached_token"] * unc
             + c["ft_per_overlap"] * max(ov_ft, 0.0), 0.0)
    dec = max(c["dec_intercept"] + c["dec_per_overlap"] * max(ov_dec, 0.0), 0.0)
    engine = ft + dec
    slack = deadline - t_submit - float(p["link_rtt_s"])
    if engine <= 0.0:
        prob = 1.0 if slack >= 0.0 else 0.0
    elif slack <= 0.0:
        prob = 0.0
    else:
        prob = _cdf(p, slack / engine)
    return {"p_hat": float(prob), "first_token_s": ft, "decode_s": dec, "engine_service_s": engine,
            "uncached_tokens": unc, "slack_s": slack,
            "ratio_at_which_evaluated": (slack / engine if engine > 0 else None),
            "model_version": p["version"], "payload_sha256": art["payload_sha256"]}


def p_hat_cold_fallback(art: Dict[str, Any], row: Dict[str, Any], history_tokens: int,
                        where: str = "P_hat cold fallback") -> Dict[str, Any]:
    """P_hat for a question whose own request carries NO `prompt_tokens`, priced as a COLD request
    of `history_tokens` with `cached_tokens = 0`. **OPT-IN, NEVER CALLED BY `evaluate_cell`.**

    Why it exists, and why it is separate. In the committed WARM-ALL cell, 7 of 20 released robot
    questions came back HTTP 400 with no `prompt_tokens`, no `cached_tokens` and no
    `t_first_token`, and nothing delivered, so `1[on time] = 0`. Those questions WERE released, so
    D157 (2)'s population includes them, and the frozen model cannot price them from the request
    log. Pricing them needs a SECOND input source (the trace's own `history_tokens` for that
    opportunity) and a ruling about the cache state to assume. **That is a population decision, not
    an implementation detail**, so this function requires the caller to pass `history_tokens`
    explicitly, labels its output, and is never reached by the default path. Its overlap counts
    still come from the cell.
    """
    if history_tokens is None or not isinstance(history_tokens, (int, float)):
        raise OnTimeInputMissing("%s: history_tokens must be supplied explicitly from the trace; "
                                 "this fallback never guesses a size." % where)
    got = p_hat(art, {**row, "prompt_tokens": float(history_tokens), "cached_tokens": 0.0},
                where=where)
    got["basis"] = "COLD_WORST_CASE_FALLBACK"
    got["basis_note"] = ("prompt_tokens from the trace's history_tokens and cached_tokens assumed "
                         "0, which is the COLD extreme: it maximises predicted service and so "
                         "MINIMISES P_hat. On a question that actually missed, a lower P_hat means "
                         "a SMALLER D157 error, so this fallback is conservative toward a NARROW "
                         "margin and must be reported as such if it is used")
    return got


def census_cell(cell_dir: Path) -> Dict[str, Any]:
    """Can the margin be computed from this cell? Counts, no pricing, no model needed.

    Run this on the EP-G WARM-ALL held-out cells THE MOMENT THEY LAND, before scoring: it reports
    how many robot questions were released, how many carry every input `P_hat` needs, and why each
    of the rest does not. A margin computed without this census inherits a denominator nobody
    looked at.
    """
    rows = features_from_cell(Path(cell_dir))
    missing: Dict[str, int] = {}
    ok = 0
    for r in rows:
        bad = [k for k in REQUIRED_INPUTS if r.get(k) is None]
        if bad:
            for k in bad:
                missing[k] = missing.get(k, 0) + 1
        else:
            ok += 1
    return {
        "cell": Path(cell_dir).name,
        "label": cell_label(Path(cell_dir)),
        "arm": cell_arm(Path(cell_dir)),
        "population_check": check_population(Path(cell_dir)),
        "robot_questions_released": len(rows),
        "priceable": ok,
        "unpriceable": len(rows) - ok,
        "missing_input_counts": missing,
        "on_time_among_unpriceable": sum(1 for r in rows
                                         if any(r.get(k) is None for k in REQUIRED_INPUTS)
                                         and r.get("actually_on_time")),
        "required_inputs": list(REQUIRED_INPUTS),
        "_why_it_matters": ("D157 (2)'s population is every robot question RELEASED. An "
                            "unpriceable question is still in the population, so the p90 is taken "
                            "over fewer points than the population holds unless the user rules how "
                            "to price them (see p_hat_cold_fallback)"),
    }


def d157_error(p: float, actually_on_time: bool, a_d2_dev: float = A_D2_DEV) -> float:
    """D157 (2): `a_D2_DEV x |P_hat - 1[actually on time]|`, in expected-correct-answer units."""
    return float(a_d2_dev) * abs(float(p) - (1.0 if actually_on_time else 0.0))


# ---------------------------------------------------------------------------
# per-question features from a scored cell


def _jl(p: Path) -> List[Dict[str, Any]]:
    import gzip                                                                # noqa: PLC0415
    for c in (p, p.with_name(p.name + ".gz")):
        if c.exists():
            op = gzip.open if str(c).endswith(".gz") else open
            with op(c, "rt") as f:
                return [json.loads(x) for x in f if x.strip()]
    raise FileNotFoundError("neither %s nor %s.gz exists" % (p, p.name))


def features_from_cell(cell_dir: Path) -> List[Dict[str, Any]]:
    """Every ROBOT QUESTION RELEASED in a cell, with the inputs `p_hat` needs.

    Overlap counts follow `cost_model_gate.features` exactly, including its filter: only requests
    carrying `t_submit`, `t_first_token`, `t_done` and `prompt_tokens` enter the overlap counts. A
    released robot question whose own request is missing one of those is NOT dropped: it is
    returned with the field absent, so `p_hat` raises on it and the scoring pass sees a refusal
    rather than a silently smaller denominator.
    """
    cell_dir = Path(cell_dir)
    req = _jl(cell_dir / "request.jsonl")
    out = _jl(cell_dir / "outcomes.jsonl")
    full = [r for r in req
            if r.get("t_submit") is not None and r.get("t_done") is not None
            and r.get("t_first_token") is not None and r.get("prompt_tokens")]
    starts = sorted(float(r["t_submit"]) for r in full)
    ends = sorted(float(r["t_done"]) for r in full)
    ft_starts = sorted(float(r["t_submit"]) for r in full)
    ft_ends = sorted(float(r["t_first_token"]) for r in full)
    dec_starts = sorted(float(r["t_first_token"]) for r in full)
    dec_ends = sorted(float(r["t_done"]) for r in full)

    def _ov(s0: float, e0: float, ss: Sequence[float], ee: Sequence[float]) -> int:
        return max(bisect.bisect_left(ss, e0) - bisect.bisect_right(ee, s0) - 1, 0)

    recalls = {o["opportunity_id"]: o for o in out
               if o.get("kind") == "recall" and o.get("opportunity_id")
               and str(o.get("session_id") or "").startswith("robo")}
    rows: List[Dict[str, Any]] = []
    for r in req:
        oid = r.get("opportunity_id")
        if oid not in recalls:
            continue
        o = recalls[oid]
        row: Dict[str, Any] = {
            "opportunity_id": oid, "question_id": o.get("question_id"),
            "device_id": o.get("device_id"), "session_id": o.get("session_id"),
            "request_id": r.get("request_id"),
            "representation": (o.get("cloud_payload") or {}).get("representation"),
        }
        for k in ("prompt_tokens", "cached_tokens", "t_submit"):
            if k in r:
                row[k] = r.get(k)
        if o.get("t_opportunity") is not None and o.get("deadline_s") is not None:
            row["deadline_abs_s"] = float(o["t_opportunity"]) + float(o["deadline_s"])
        if (r.get("t_submit") is not None and r.get("t_first_token") is not None
                and r.get("t_done") is not None):
            s, a, b = float(r["t_submit"]), float(r["t_first_token"]), float(r["t_done"])
            row["overlap_ft"] = _ov(s, a, ft_starts, ft_ends)
            row["overlap_decode"] = _ov(a, b, dec_starts, dec_ends)
            row["actual_engine_service_s"] = b - s
        td = o.get("t_delivered")
        row["actually_on_time"] = bool(
            td is not None and o.get("t_opportunity") is not None
            and float(td) - float(o["t_opportunity"]) <= float(o.get("deadline_s") or 0.0))
        row["_on_time_rule"] = ("t_delivered - t_opportunity <= deadline_s, the run scorer's own "
                                "rule (hybrid/feasible_on_time.py)")
        rows.append(row)
    rows.sort(key=lambda x: str(x.get("opportunity_id")))
    return rows


def evaluate_cell(cell_dir: Path, art: Optional[Dict[str, Any]] = None,
                  strict: bool = True) -> Dict[str, Any]:
    """P_hat and D157 (2)'s per-question error for every released robot question in one cell.

    `strict` controls what a refusal does, not whether one happens: with `strict` the first missing
    input aborts; without it, the refusals are collected and COUNTED beside the rows, so a scoring
    pass can see how many questions could not be priced instead of inheriting a quiet denominator.
    """
    art = art or load()
    rows = features_from_cell(Path(cell_dir))
    priced, refused = [], []
    for r in rows:
        try:
            got = p_hat(art, r, where="cell %s, opportunity %s"
                                     % (Path(cell_dir).name, r.get("opportunity_id")))
        except OnTimeInputMissing as e:
            if strict:
                raise
            refused.append({"opportunity_id": r.get("opportunity_id"), "reason": str(e)[:240]})
            continue
        e = d157_error(got["p_hat"], bool(r["actually_on_time"]), float(art["payload"]["a_D2_DEV"]))
        priced.append({**r, **got, "d157_error": e})
    return {
        "cell": Path(cell_dir).name,
        "cell_label": cell_label(Path(cell_dir)),
        "arm": cell_arm(Path(cell_dir)),
        "n_robot_questions_released": len(rows),
        "n_priced": len(priced), "n_refused": len(refused), "refusals": refused,
        "rows": priced,
        "model_version": art["payload"]["version"],
        "payload_sha256": art["payload_sha256"], "code_sha256": art["code_sha256"],
    }


# ---------------------------------------------------------------------------
# the margin, with D157 (2)'s population guard


def cell_label(cell_dir: Path) -> Optional[str]:
    p = cell_dir / "run_meta.json"
    if not p.exists():
        return None
    try:
        return str(json.loads(p.read_text()).get("label"))
    except Exception:                                                          # noqa: BLE001
        return None


def cell_arm(cell_dir: Path) -> Optional[str]:
    p = cell_dir / "cell.json"
    if not p.exists():
        return None
    try:
        return str(json.loads(p.read_text()).get("arm"))
    except Exception:                                                          # noqa: BLE001
        return None


def check_population(cell_dir: Path) -> Dict[str, Any]:
    """Is this cell in D157 (2)'s declared population? Reports, and never guesses."""
    label = cell_label(Path(cell_dir))
    arm = cell_arm(Path(cell_dir))
    problems: List[str] = []
    if label is None:
        problems.append("run_meta.json::label is absent, so the cell does not declare its workload")
    if arm != POPULATION_ARM:
        problems.append("cell.json::arm is %r and the population is %r" % (arm, POPULATION_ARM))
    for s in POPULATION_LABEL_REQUIRED:
        if label is None or s not in label:
            problems.append("label does not contain %r" % s)
    for s in POPULATION_LABEL_FORBIDDEN:
        if label is not None and s in label:
            problems.append("label contains %r, which the population excludes" % s)
    return {"cell": Path(cell_dir).name, "arm": arm, "label": label,
            "in_population": not problems, "problems": problems}


def margin_from_cells(cell_dirs: Sequence[Path], art: Optional[Dict[str, Any]] = None,
                      expect_n_cells: int = 4) -> Dict[str, Any]:
    """MARGIN_CF = p90 of `0.250 x |P_hat - 1[on time]|` over D157 (2)'s population.

    REFUSES unless every cell declares itself in the population and there are exactly the four
    cells D157 (2) names. The guard is the point: a margin computed over the wrong cells would be
    a number nobody could tell apart from the right one.
    """
    art = art or load()
    checks = [check_population(Path(c)) for c in cell_dirs]
    bad = [c for c in checks if not c["in_population"]]
    if bad or len(cell_dirs) != expect_n_cells:
        raise MarginPopulationRefused(json.dumps({
            "refused": ("D157 (2) fixes the population as the 4 EP-G WARM-ALL held-out cells "
                        "(upload-pf) and no other cells"),
            "n_cells_given": len(cell_dirs), "n_cells_expected": expect_n_cells,
            "looked_for": {"arm": POPULATION_ARM,
                           "label_must_contain": list(POPULATION_LABEL_REQUIRED),
                           "label_must_not_contain": list(POPULATION_LABEL_FORBIDDEN)},
            "checks": checks,
            "if_the_labels_differ": ("the cells may be in the population and merely labelled "
                                     "differently. That is a question for the coordinator, not "
                                     "something this function may assume"),
        }, indent=1))
    errs: List[float] = []
    per_cell = []
    for c in cell_dirs:
        ev = evaluate_cell(Path(c), art, strict=True)
        e = [r["d157_error"] for r in ev["rows"]]
        errs.extend(e)
        per_cell.append({"cell": ev["cell"], "n": ev["n_priced"], "n_refused": ev["n_refused"],
                         "mean_error": (sum(e) / len(e) if e else None)})
    errs.sort()

    def _q(p: float) -> float:
        pos = p * (len(errs) - 1)
        lo = int(math.floor(pos))
        hi = min(lo + 1, len(errs) - 1)
        return float(errs[lo] + (errs[hi] - errs[lo]) * (pos - lo))

    return {
        "MARGIN_CF": round(_q(0.90), 9),
        "statistic": "p90 of a_D2_DEV x |P_hat - 1[actually on time]| per robot question",
        "a_D2_DEV": float(art["payload"]["a_D2_DEV"]),
        "n_questions": len(errs),
        "quantiles": {("p%g" % (p * 100)): round(_q(p), 9)
                      for p in (0.0, 0.25, 0.5, 0.75, 0.9, 0.99, 1.0)},
        "per_cell": per_cell,
        "population_checks": checks,
        "model_version": art["payload"]["version"],
        "payload_sha256": art["payload_sha256"], "code_sha256": art["code_sha256"],
        "_next_step": ("this number is MARGIN_CF under D157 (2). Setting it is an edit to "
                       "v5/cf_margin.py::MARGIN_CF, made ONCE, with this output's two hashes "
                       "recorded beside it, and never swept afterwards"),
    }


# ---------------------------------------------------------------------------


def verify(art_path: Path = ARTEFACT) -> Dict[str, Any]:
    """Both hashes, plus a drift check against the planner's live path in `cf_cost`."""
    art = load(art_path, verify=True)
    drift = {"checked": False}
    try:
        import cf_cost as CC                                                   # noqa: PLC0415
        m = CC.load_gate_model()
        res = CC.load_residuals()
        rows = []
        for tokens, cached, ov in ((7051, 0, 6), (21000, 3000, 0), (467, 0, 14)):
            pred = CC.predict(m, tokens, cached, ov, ov)
            live = CC.p_on_time(res, pred.engine_s, 3.0 - CC.LINK_RTT_S)
            froz = p_hat(art, {"prompt_tokens": tokens, "cached_tokens": cached,
                               "overlap_ft": ov, "overlap_decode": ov,
                               "t_submit": 0.0, "deadline_abs_s": 3.0})
            rows.append({"tokens": tokens, "cached": cached, "overlap": ov,
                         "frozen_p_hat": round(froz["p_hat"], 12),
                         "live_cf_cost": round(live, 12),
                         "abs_diff": abs(froz["p_hat"] - live)})
        drift = {"checked": True, "rows": rows,
                 "max_abs_diff": max(r["abs_diff"] for r in rows),
                 "agree": all(r["abs_diff"] < 1e-12 for r in rows),
                 "note": ("the frozen prediction is self-contained; this only REPORTS whether the "
                          "planner's live path still agrees with it. Drift is information, not a "
                          "reason to change the frozen numbers")}
    except Exception as e:                                                     # noqa: BLE001
        drift = {"checked": False, "error": str(e)[:200]}
    return {"artefact": str(art_path.relative_to(REPO)),
            "payload_sha256": art["payload_sha256"], "code_sha256": art["code_sha256"],
            "version": art["payload"]["version"], "hashes_verified": True,
            "drift_vs_cf_cost": drift}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="the frozen on-time model P_hat (D157 (2))")
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--evaluate", metavar="CELL_DIR")
    ap.add_argument("--census", metavar="CELL_DIR",
                    help="counts only: can the margin be computed from this cell")
    ap.add_argument("--margin", nargs="*", metavar="CELL_DIR",
                    help="the 4 EP-G WARM-ALL held-out cells; refuses anything else")
    args = ap.parse_args(argv)
    if args.freeze:
        art = freeze()
        print("froze %s" % ARTEFACT.relative_to(REPO))
        print("version       %s" % art["payload"]["version"])
        print("payload_sha256 %s" % art["payload_sha256"])
        print("code_sha256    %s" % art["code_sha256"])
        return 0
    if args.verify:
        print(json.dumps(verify(), indent=1))
        return 0
    if args.census:
        print(json.dumps(census_cell(Path(args.census)), indent=1))
        return 0
    if args.evaluate:
        ev = evaluate_cell(Path(args.evaluate), strict=False)
        ev["rows"] = ev["rows"][:5]
        print(json.dumps(ev, indent=1))
        return 0
    if args.margin is not None:
        print(json.dumps(margin_from_cells([Path(c) for c in args.margin]), indent=1))
        return 0
    art = load()
    print(json.dumps({"version": art["payload"]["version"],
                      "payload_sha256": art["payload_sha256"],
                      "code_sha256": art["code_sha256"],
                      "required_inputs": list(REQUIRED_INPUTS),
                      "formula": art["payload"]["formula"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
