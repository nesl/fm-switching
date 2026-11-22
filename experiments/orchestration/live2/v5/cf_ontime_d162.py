"""P_hat REBUILT ON THE D162 MODEL (D169 step 1). CPU only.

    python3 -I experiments/orchestration/live2/v5/cf_ontime_d162.py --freeze
    python3 -I experiments/orchestration/live2/v5/cf_ontime_d162.py --verify

WHY A NEW MODULE RATHER THAN AN EDIT. The committed `cf_ontime_frozen.py` hashes its own source,
so editing it breaks its freeze loudly, which is the behaviour that file was designed to have. It
also rests on the gate model that FAILED (`cost_model_gate.json`, the by_arm split). D169 orders a
rebuild on the D162 model, so this is a deliberate, visible re-freeze into a NEW artefact, and the
old one stays byte-verifiable as the record of what the margin would have been.

WHAT CHANGED, and it is the formula's SHAPE and not only its numbers:

    old   first_token = a0 + a1 x uncached + a2 x overlap_ft          (overlap COUNT)
          decode      = b0 + b1 x overlap_decode                      (overlap COUNT)
    new   first_token = a0 + a1 x uncached + a2 x queue_uncached_ahead (queued WORK)
          decode      = b0 + b1 x queue_decode_ahead                  (queued WORK)

D159 (B) required the count to become work, because what a queue makes you wait for is work, and
the 160x overlap spread is what broke the linear form. The coefficients are non-negative by
construction (NNLS), so a prediction cannot be negative, which is the failure that sank D156 (4).

UNCHANGED, deliberately: the rest of the formula, so the margin's definition is not quietly
redefined along with its inputs.

    engine_service = first_token + decode
    slack          = deadline_abs_s - t_submit - link_rtt_s
    P_hat          = F_ratio(slack / engine_service)

F_ratio is the empirical CDF of ACTUAL over PREDICTED engine service, linearly interpolated, 0
below its support and 1 above. It is recomputed here on the D162 HELD-OUT set (seed-5 healthy
sweep requests), because a residual CDF belongs to the model that produced it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics as st
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
LIVE2 = HERE.parent
REPO = LIVE2.parents[2]
for _p in (str(LIVE2), str(LIVE2 / "fleet"), str(REPO / "experiments/orchestration/baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

VERSION = "cf-ontime-d162-1.0"
A_D2_DEV = 0.250
LINK_RTT_S = 0.044
GATE_JSON = REPO / "results/orchestration/live2/frozen_test/cost_model_gate_d162.json"
ARTEFACT = REPO / "results/orchestration/live2/v5/cf_ontime_model_d162.json"
N_Q = 1001

FORMULA = (
    "first_token = ft_intercept + ft_per_uncached_token x max(prompt_tokens - cached_tokens, 0) "
    "+ ft_per_queue_token x queue_uncached_ahead; decode = dec_intercept "
    "+ dec_per_queue_decode_token x queue_decode_ahead; engine_service = first_token + decode; "
    "slack = deadline_abs_s - t_submit - link_rtt_s; P_hat = F_ratio(slack / engine_service), "
    "F_ratio the empirical CDF of actual-over-predicted engine service on the D162 HELD-OUT "
    "healthy-regime requests, linearly interpolated, 0 below its support and 1 above it.")


class FrozenModelTampered(RuntimeError):
    pass


class OnTimeInputMissing(RuntimeError):
    pass


def _canonical(o: Any) -> str:
    return json.dumps(o, sort_keys=True, separators=(",", ":"), default=str)


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def code_sha256() -> str:
    return hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()


def _held_out_rows():
    """The D162 held-out healthy rows, rebuilt from the same cells the gate used."""
    import cost_model_gate_d162 as G
    rows = []
    for n in G.NS:
        d = G.cell_dir(n, G.TEST_SEED)
        r = G.features(d)
        if not r:
            continue
        G.classify(r)
        rows += [x for x in r if x["zone"] == "healthy"]
    return rows


def build_payload() -> Dict[str, Any]:
    gate = json.loads(GATE_JSON.read_text())
    if gate.get("verdict") != "PASS":
        raise RuntimeError(
            "the D162 gate artefact does not say PASS (%r). P_hat is not rebuilt on a model whose "
            "own gate has not passed; D169 ordered this rebuild AFTER the pass."
            % (gate.get("verdict"),))
    m = gate["model"]
    ft, dec = m["first_token"], m["decode"]
    rows = _held_out_rows()
    if not rows:
        raise RuntimeError("no D162 held-out healthy rows found; cannot build the residual CDF")
    ratios: List[float] = []
    for r in rows:
        pred = (ft["intercept"] + ft["per_uncached_token"] * r["uncached_tokens"]
                + ft["per_queue_token"] * r["queue_uncached_ahead"]
                + dec["intercept"] + dec["per_queue_decode_token"] * r["queue_decode_ahead"])
        act = float(r["first_token_s"]) + float(r["decode_s"])
        if pred > 1e-9:
            ratios.append(act / pred)
    ratios.sort()
    qs = [i / (N_Q - 1) for i in range(N_Q)]
    vals = [ratios[min(int(round(q * (len(ratios) - 1))), len(ratios) - 1)] for q in qs]
    warm = sum(1 for r in rows if r["warm"])
    return {
        "version": VERSION,
        "formula": FORMULA,
        "a_D2_DEV": A_D2_DEV,
        "link_rtt_s": LINK_RTT_S,
        "coefficients": {
            "ft_intercept": float(ft["intercept"]),
            "ft_per_uncached_token": float(ft["per_uncached_token"]),
            "ft_per_queue_token": float(ft["per_queue_token"]),
            "dec_intercept": float(dec["intercept"]),
            "dec_per_queue_decode_token": float(dec["per_queue_decode_token"]),
        },
        "ratio_cdf": {"q": qs, "value": [float(v) for v in vals]},
        "ratio_summary": {"n": len(ratios), "p10": round(vals[100], 6),
                          "p50": round(vals[500], 6), "p90": round(vals[900], 6)},
        "sources": {
            "gate_model": {"file": str(GATE_JSON.relative_to(REPO)),
                           "sha256": hashlib.sha256(GATE_JSON.read_bytes()).hexdigest(),
                           "verdict": gate.get("verdict"),
                           "criteria": gate.get("criteria")},
            "residuals": {"derived_here_from": "the D162 held-out healthy rows (seed-5 sweep)",
                          "n_rows": len(rows), "warm_rows": warm},
        },
        "supersedes": {
            "file": "results/orchestration/live2/v5/cf_ontime_model_frozen.json",
            "why": ("it rests on cost_model_gate.json, the by_arm split, whose own gate FAILED and "
                    "whose warm_rows_held_out was 0. Left intact and byte-verifiable as the record "
                    "of what the margin would have been."),
        },
    }


def load() -> Dict[str, Any]:
    d = json.loads(ARTEFACT.read_text())
    if d.get("payload_sha256") != _sha(_canonical(d["payload"])):
        raise FrozenModelTampered("payload hash mismatch")
    if d.get("code_sha256") != code_sha256():
        raise FrozenModelTampered(
            "code hash mismatch: this module changed since the freeze, so the arithmetic behind "
            "the frozen numbers is not the arithmetic now in the file. Re-freeze deliberately.")
    return d["payload"]


def _f_ratio(payload: Dict[str, Any], x: float) -> float:
    v = payload["ratio_cdf"]["value"]
    q = payload["ratio_cdf"]["q"]
    if x <= v[0]:
        return 0.0
    if x >= v[-1]:
        return 1.0
    lo, hi = 0, len(v) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if v[mid] <= x:
            lo = mid
        else:
            hi = mid
    span = v[hi] - v[lo]
    t = 0.0 if span <= 0 else (x - v[lo]) / span
    return float(q[lo] + t * (q[hi] - q[lo]))


def p_on_time(payload: Dict[str, Any], row: Dict[str, Any]) -> float:
    """P_hat for one robot question's own cloud request. A missing input RAISES."""
    need = ("prompt_tokens", "cached_tokens", "queue_uncached_ahead", "queue_decode_ahead",
            "t_submit", "deadline_abs_s")
    for k in need:
        if row.get(k) is None:
            raise OnTimeInputMissing(
                "%s is missing for this question; P_hat never defaults an input (a cached_tokens "
                "of None is a missing input, not a zero)" % k)
    c = payload["coefficients"]
    unc = max(int(row["prompt_tokens"]) - int(row["cached_tokens"]), 0)
    pred = (c["ft_intercept"] + c["ft_per_uncached_token"] * unc
            + c["ft_per_queue_token"] * float(row["queue_uncached_ahead"])
            + c["dec_intercept"]
            + c["dec_per_queue_decode_token"] * float(row["queue_decode_ahead"]))
    slack = float(row["deadline_abs_s"]) - float(row["t_submit"]) - payload["link_rtt_s"]
    if pred <= 1e-9:
        return 1.0 if slack > 0 else 0.0
    return _f_ratio(payload, slack / pred)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    if a.freeze:
        payload = build_payload()
        art = {"label": "P_hat rebuilt on the D162 model (D169 step 1)",
               "payload": payload,
               "payload_sha256": _sha(_canonical(payload)),
               "code_file": str(Path(__file__).resolve().relative_to(REPO)),
               "code_sha256": code_sha256()}
        ARTEFACT.parent.mkdir(parents=True, exist_ok=True)
        ARTEFACT.write_text(json.dumps(art, indent=1))
        print(f"froze {ARTEFACT.relative_to(REPO)}")
        print(f"  version        {payload['version']}")
        print(f"  coefficients   {payload['coefficients']}")
        print(f"  ratio CDF      n={payload['ratio_summary']['n']} "
              f"p10={payload['ratio_summary']['p10']} p50={payload['ratio_summary']['p50']} "
              f"p90={payload['ratio_summary']['p90']}")
        print(f"  payload_sha256 {art['payload_sha256']}")
        print(f"  code_sha256    {art['code_sha256']}")
        return
    if a.verify:
        p = load()
        print(f"VERIFIED {p['version']}: payload and code hashes both match")
        return
    ap.print_help()


if __name__ == "__main__":
    main()
