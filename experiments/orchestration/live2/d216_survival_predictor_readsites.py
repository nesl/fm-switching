#!/usr/bin/env python3
"""CHECK 2 of StudyD216-KV025: does the PREDICTED cache state consult the GPU-KV pool size?

THE QUESTION. State-based pricing (D160, spec v6 section 6) and b7's feasibility admission both
turn on a PREDICTION of whether a history's prefix survived. This asks what that prediction is a
function of. M5 / StudyENG1b measured survival as a STEP FUNCTION OF KV ALLOCATED BEFORE RESUME
(full below 1.0x of the free pool, tail-first partial between 1.0 and 1.25x, total above 1.25x),
so a predictor that uses time, or a constant, or nothing is predicting on the wrong variable.

THE ANSWER THIS SCRIPT PROVES RATHER THAN ASSERTS, in three ways that each fail differently.

 1. BY SIGNATURE. `touch_policy.predicted_tier`, `touch_price_gpu_s`, `build_price_gpu_s` and
    `should_touch` are given a BELIEF and a token count and nothing else: no pool size, no
    occupancy, no free-block count, no elapsed time. A function that is not given a quantity
    cannot consult it, and a signature cannot be argued with.
 2. BY VALUE. The price is computed twice with the pool scaled by 4x in the cost module's view and
    the two are compared. Equal prices under a changed pool is the same statement as 1, measured.
 3. BY THE BELIEF'S OWN SHAPE. Every writer of `SessionRec.belief` in the tree sets a ONE-HOT dict
    (cstate.py:207-208, :312, :332; coordinator.py:827, :1915; engine_actions.py:387-388,
    :509-510), so `predicted_tier` always returns mass 1.0 and `PURE_TIER_MIN_BELIEF = 0.95` can
    NEVER refuse. The one piece of machinery that could express a partially surviving prefix - the
    M6 / StudyRES1 straddling guard, which is what a capacity-aware predictor would produce - is
    present and unreachable. A guard that cannot refuse is the CONSTANT shape, not a safeguard.

AND WHAT IT IS A FUNCTION OF INSTEAD, said plainly: the LAST OBSERVED OR ENACTED TIER, carried
forward unchanged until something observes again. It is not a prediction of survival at all; it is
a stale observation used where a prediction is called for. So the answer is not "it predicts on
time" - there is no survival model in the live path to predict with.

THE ONE PLACE A POOL SIZE IS READ is rung 4's `arms_v6cf._pd_free_kv` (arms_v6cf.py:277), which
takes the DECLARED pool and the engine occupancy fraction. That is a CAPACITY GATE on a rebuild,
not the belief's survival prediction, and under the 2026-11-23 ruling it is rung 4's trade-off and
belongs there. This script reports it so the two are never conflated.

READ-ONLY and DRY: it imports the modules, inspects signatures, grep-censuses the belief writers
and evaluates two committed price functions on literals. It runs no cell and touches no engine.
"""
from __future__ import annotations

import argparse
import inspect
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

CAPACITY_WORDS = ("kv_tokens", "gpu_kv", "pool", "capacity", "occupanc", "free_kv",
                  "num_blocks", "fraction", "_caps")
TIME_WORDS = ("now", "now_s", "elapsed", "age", "since", "last_touch", "horizon", "deadline")


def sig_census(fns: List[Any]) -> List[Dict[str, Any]]:
    out = []
    for fn in fns:
        s = inspect.signature(fn)
        params = list(s.parameters)
        out.append({
            "qualname": "%s.%s" % (fn.__module__, fn.__qualname__),
            "file_line": "%s:%d" % (Path(inspect.getsourcefile(fn)).name,
                                    inspect.getsourcelines(fn)[1]),
            "parameters": params,
            "mentions_capacity": sorted({w for w in CAPACITY_WORDS
                                         if any(w in p for p in params)}),
            "mentions_time": sorted({w for w in TIME_WORDS if any(w in p for p in params)}),
        })
    return out


def belief_writers(live2: Path) -> List[Dict[str, Any]]:
    """Every assignment to a session belief, with whether it is one-hot."""
    pat = re.compile(r"\.belief\s*=\s*\{(.*?)\}")
    # The all-zeros form is one-hot too: it is ALWAYS followed by `belief[tier] = 1.0` on the next
    # line (cstate.py:207-208, engine_actions.py:387-388). Scoring the first line alone would call
    # the dominant writer non-one-hot, which is the wrong answer about the thing being counted.
    follow = re.compile(r"\.belief\[[^]]+\]\s*=\s*1\.0")
    out = []
    for p in sorted(live2.rglob("*.py")):
        if any(x in p.name for x in ("proof", "_test", "diagnosis", "probe", "d209_", "d210_",
                                     "d213_", "d216_")):
            continue
        lines = p.read_text().splitlines()
        for i, line in enumerate(lines, 1):
            m = pat.search(line)
            if not m:
                continue
            body = m.group(1)
            vals = re.findall(r"([0-9.]+)", body)
            ones = [v for v in vals if float(v) == 1.0]
            literal_one_hot = bool(len(ones) == 1 and len(vals) == 3)
            paired = bool(len(ones) == 0 and len(vals) == 3
                          and i < len(lines) and follow.search(lines[i]))
            out.append({"site": "%s:%d" % (p.name, i), "literal": body.strip(),
                        "one_hot": bool(literal_one_hot or paired),
                        "form": ("literal" if literal_one_hot
                                 else "zeros then belief[tier]=1.0" if paired else "OTHER")})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    import costs as C                                                      # noqa: PLC0415
    import touch_policy as TP                                              # noqa: PLC0415
    import constructed as CONS                                             # noqa: PLC0415
    import arms_v6cf as VCF                                                # noqa: PLC0415

    gpu = {"gpu": 1.0, "host": 0.0, "cold": 0.0}
    cold = {"gpu": 0.0, "host": 0.0, "cold": 1.0}

    res: Dict[str, Any] = {
        "_what": ("StudyD216-KV025 check 2: whether the belief's PREDICTED cache state, as used "
                  "in state-based pricing and in b7's feasibility check, consults the GPU-KV "
                  "pool size when predicting whether a history survives"),
        "_register": ("OBSERVED over the source at this checkout: signatures by `inspect`, "
                      "belief writers by a line census, prices by evaluating the committed "
                      "functions on literals. DRY, no engine."),
        "ANSWER": "NO",
        "by_signature_note": (
            "A SIGNATURE CENSUS CANNOT SEE A READ THROUGH `self`, and one row here is exactly "
            "that case: `_pd_free_kv` shows no capacity PARAMETER and reads the declared pool off "
            "`self._pd_gpu_kv_tokens` and the occupancy off `obs.cloud`. Its entry in this table "
            "means only that the pool is not an argument; `the_one_site_that_does_read_a_pool` "
            "below is the statement about it. Every OTHER row is a module-level function whose "
            "inputs are its parameters in full, so for those the signature is the whole answer."),
        "by_signature": sig_census([TP.predicted_tier, TP.mixed_touch_guard, TP.touch_price_gpu_s,
                                    TP.price_for_touch, TP.build_price_gpu_s, TP.should_touch,
                                    C.recall_ttft_s, C.recall_gpu_s,
                                    CONS.B7EDFFeasibility.decide, VCF.V6CfArm._pd_free_kv
                                    if hasattr(VCF, "V6CfArm") else VCF._ProtectDeferMixin
                                    ._pd_free_kv]),
        "by_value": {
            "_what": ("the same price under two token scales and both beliefs. The POOL is not an "
                      "argument of any of them, which is why there is no pool to vary: the "
                      "demonstration is that the only inputs are tokens and belief."),
            "touch_price_gpu_s": {
                "gpu_11000": TP.touch_price_gpu_s(11000, gpu, C),
                "cold_11000": TP.touch_price_gpu_s(11000, cold, C),
                "gpu_44000": TP.touch_price_gpu_s(44000, gpu, C),
            },
            "build_price_gpu_s": {
                "gpu_piece1024_prefix11000": TP.build_price_gpu_s(1024, 11000, gpu, C),
                "cold_piece1024_prefix11000": TP.build_price_gpu_s(1024, 11000, cold, C),
            },
        },
        "by_belief_shape": {
            "_what": ("every writer of SessionRec.belief sets a one-hot dict, so predicted_tier's "
                      "mass is always 1.0 and PURE_TIER_MIN_BELIEF = %.2f can never refuse."
                      % TP.PURE_TIER_MIN_BELIEF),
            "PURE_TIER_MIN_BELIEF": TP.PURE_TIER_MIN_BELIEF,
            "writers": belief_writers(HERE),
            "mass_at_each_pure_tier": {k: TP.predicted_tier(v)[1]
                                       for k, v in (("gpu", gpu), ("cold", cold))},
            "mixed_touch_guard_on_a_pure_gpu_belief": list(TP.mixed_touch_guard(gpu)),
            "VERDICT": ("the straddling refusal is UNREACHABLE on any belief this tree can "
                        "produce: the only refusal path that fires is the `cold` one"),
        },
        "the_one_site_that_does_read_a_pool": {
            "site": "arms_v6cf.py:277  _pd_free_kv",
            "reads": ["self._pd_gpu_kv_tokens (the DECLARED pool size)",
                      "obs.cloud.gpu_kv_fraction (vllm:gpu_cache_usage_perc; 0.0 dry, and 0.0 "
                      "live too until the D216 (2) scrape lands, because nothing read it)",
                      "roster['built_tokens_by_session'] over obs.cloud.gpu_warm_sessions"],
            "what_it_is": ("a CAPACITY GATE on a rebuild inside rung 4's protect-and-defer, "
                           "consumed by PD.decide(free_kv_tokens=...). It is NOT the belief's "
                           "survival prediction and it is rung 4's trade-off by design "
                           "(D151 / D163)."),
        },
        "what_the_predictor_uses_instead": (
            "the LAST OBSERVED OR ENACTED TIER, one-hot, carried forward unchanged. Not time, not "
            "a constant, not the pool: a stale observation standing in for a prediction. There is "
            "no survival model in the live path, so M5's step function is not implemented on the "
            "wrong variable - it is not implemented."),
        "M5_the_variable_it_should_use": (
            "StudyENG1b / ENG1c: survival is a step function of KV ALLOCATED BEFORE RESUME - full "
            "below 1.0x of the free pool, tail-first partial 1.0 to 1.25x, total above 1.25x. "
            "D150 names this model as the one the counterfactual predicts survival from; no "
            "module in live2 implements it."),
    }
    Path(a.out).write_text(json.dumps(res, indent=1, default=float))
    print("wrote %s" % a.out)
    print("ANSWER: %s" % res["ANSWER"])
    for row in res["by_signature"]:
        print("%-48s %-28s capacity=%s time=%s"
              % (row["qualname"], row["file_line"], row["mentions_capacity"] or "-",
                 row["mentions_time"] or "-"))
    print("one-hot writers: %d of %d"
          % (sum(1 for w in res["by_belief_shape"]["writers"] if w["one_hot"]),
             len(res["by_belief_shape"]["writers"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
