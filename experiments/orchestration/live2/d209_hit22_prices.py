#!/usr/bin/env python3
"""D209 (2) hit 22: the touch-price distribution BEFORE and AFTER, paired on identical inputs,
plus the budget refusals the correction removes, on one dry cell.

HOW THE PAIRING IS DONE, and why it is not two cells differenced. `touch_policy.price_for_touch`
is TAPPED, not replaced: the tap calls the module's own function for the result the run uses, and
ALSO computes the other mode's price on the SAME (prefix_tokens, belief) input, and asks the SAME
budget whether it would refuse each. So the two columns are the two prices of the same touch,
rather than the prices of two different runs' touches, which is the only form in which a
distribution comparison means anything here. The tap returns the committed result unchanged, so no
decision moves because of it.

The per-arm counters (`touch_considered`, `touch_refused_budget`, `touch_issued`) are read from the
cell's own stats, so the OBSERVED refusal change is reported beside the paired construction and is
not inferred from it. Register, per CLAUDE.md: the paired column is a CONSTRUCTED counterfactual on
observed inputs; the counters are an OBSERVED census of this cell.

Run once per tree. The posted knobs and the one-cell-per-process rule are the committed recipe's.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path
from typing import Any, Dict, List

POSTED = dict(ratio="40:40:20", robot_question_set="lh_req", ss_question_set="ss2",
              dashcam_format="epg", robot_upload="per-frame", robot_reask_mean_s=30.0)


def quantiles(v: List[float]) -> Dict[str, Any]:
    if not v:
        return {"n": 0}
    s = sorted(v)
    def q(p: float) -> float:
        return s[min(len(s) - 1, int(p * len(s)))]
    return {"n": len(s), "min": s[0], "p10": q(0.10), "p50": q(0.50), "p90": q(0.90),
            "max": s[-1], "mean": st.fmean(s),
            "iqr": [q(0.25), q(0.75)], "n_distinct": len(set(s))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", required=True)
    ap.add_argument("--arm", default="covex-v6-state-uo-c5attr")
    ap.add_argument("--seed", type=int, default=4)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    live2 = Path(a.tree) / "experiments/orchestration/live2"
    for p in (live2, live2 / "fleet", live2 / "v5", live2 / "hybrid", live2 / "tests",
              live2.parent, live2.parent / "baselines", live2.parent / "sim",
              live2.parent.parent / "lib"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

    import arms as A                                                           # noqa: F401
    import arms_v6c5 as VC
    import arms_v6cf as VCF
    import arms_v6shares as VSH
    import arms_v6state as VS
    VS.register(); VC.register(); VSH.register(); VCF.register()

    import cf_instrument as CI
    for nm in dir(CI):
        o = getattr(CI, nm)
        if isinstance(o, type) and hasattr(o, "over_budget"):
            o.over_budget = lambda self, budget_ms=None: False

    import d162_price as DP
    import touch_policy as TP
    rec: List[Dict[str, Any]] = []
    orig = TP.price_for_touch

    def _d174(prefix_tokens, belief, costs):
        """The ruled price, available in BOTH trees so the pairing is the same arithmetic on each
        side. In the after tree it is the module's own function; in the before tree, where that
        function does not exist yet, it is the same one line of `d162_price` the after tree calls,
        so the before column is not a re-derivation with different coefficients."""
        if hasattr(TP, "touch_price_gpu_s_d174"):
            return TP.touch_price_gpu_s_d174(prefix_tokens, belief, costs)
        tier, _ = TP.predicted_tier(belief)
        if tier != "gpu":
            return float(costs.recall_gpu_s(max(int(prefix_tokens), 1), TP.READINESS[tier]))
        return float(DP.price_gpu_s(TP.TOUCH_UNCACHED_TOKENS, 0, "uncached-only"))

    orig_should = TP.should_touch

    def tapped_should(*, belief, prefix_tokens, costs, budget_ok=None):
        d = orig_should(belief=belief, prefix_tokens=prefix_tokens, costs=costs,
                        budget_ok=budget_ok)
        reload_proxy = TP.touch_price_gpu_s(prefix_tokens, belief, costs)
        d174 = _d174(prefix_tokens, belief, costs)
        d162 = TP.touch_price_gpu_s_d162(prefix_tokens, belief, costs)
        tier, mass = TP.predicted_tier(belief)
        allowed, _why = TP.mixed_touch_guard(belief)
        # the SAME budget, asked about each price, at the same instant in the run
        ok_reload = (None if budget_ok is None else bool(budget_ok(reload_proxy)))
        ok_d174 = (None if budget_ok is None else bool(budget_ok(d174)))
        rec.append({"prefix_tokens": int(prefix_tokens), "tier": tier, "mass": round(mass, 4),
                    "guard_allowed": bool(allowed),
                    "live": d["price_gpu_s"], "reload_proxy": reload_proxy, "d174": d174,
                    "d162": d162, "budget_ok_reload_proxy": ok_reload,
                    "budget_ok_d174": ok_d174, "decided_touch": bool(d["touch"]),
                    "reason": d["reason"][:90]})
        return d
    TP.should_touch = tapped_should

    import test_hybrid as TH
    kw = {k: v for k, v in POSTED.items()
          if k in ("dashcam_format", "robot_upload", "robot_reask_mean_s")}
    rows, stats = TH.dry(a.arm, a.seed, 16, run_s=1200.0, ratio=POSTED["ratio"],
                         robot_question_set=POSTED["robot_question_set"],
                         ss_question_set=POSTED["ss_question_set"], **kw)
    stats = dict(stats or {})

    gpu = [r for r in rec if r["tier"] == "gpu"]
    ratios = [r["reload_proxy"] / r["d174"] for r in gpu
              if r.get("d174") and r["d174"] > 0]
    doc = {
        "tree": a.tree, "arm": a.arm, "seed": a.seed, "rows": len(rows or []),
        "touch_price_mode_in_this_tree": TP.TOUCH_PRICE_MODE,
        "n_price_calls": len(rec), "n_price_calls_gpu_tier": len(gpu),
        "distribution": {
            "live_this_tree": quantiles([r["live"] for r in rec]),
            "reload_proxy_all_tiers": quantiles([r["reload_proxy"] for r in rec]),
            "reload_proxy_gpu_tier": quantiles([r["reload_proxy"] for r in gpu]),
            "d174_gpu_tier": quantiles([r["d174"] for r in gpu if r["d174"] is not None]),
            "d162_gpu_tier": quantiles([r["d162"] for r in gpu]),
            "prefix_tokens_gpu_tier": quantiles([float(r["prefix_tokens"]) for r in gpu]),
            "overcharge_ratio_reload_over_d174": quantiles(ratios)},
        "paired_budget_verdicts": {
            "n_with_budget": sum(1 for r in rec if r["budget_ok_reload_proxy"] is not None),
            "refused_at_reload_proxy": sum(1 for r in rec
                                           if r["budget_ok_reload_proxy"] is False),
            "refused_at_d174": sum(1 for r in rec if r["budget_ok_d174"] is False),
            "refusals_removed_by_d174": sum(1 for r in rec
                                            if r["budget_ok_reload_proxy"] is False
                                            and r["budget_ok_d174"] is True),
            "refusals_added_by_d174": sum(1 for r in rec
                                          if r["budget_ok_reload_proxy"] is True
                                          and r["budget_ok_d174"] is False),
            "refused_at_reload_proxy_and_guard_allowed": sum(
                1 for r in rec if r["budget_ok_reload_proxy"] is False and r["guard_allowed"])},
        "touch_counters": {k: v for k, v in sorted(stats.items()) if "touch" in str(k)},
        "budget_counters": {k: v for k, v in sorted(stats.items())
                            if "budget" in str(k) or "refus" in str(k)},
        "decisions": stats.get("decisions"), "state_decisions": stats.get("state_decisions"),
        "sample_calls": rec[:5],
    }
    Path(a.out).write_text(json.dumps(doc, indent=1, default=float) + "\n")
    print(json.dumps({k: doc[k] for k in ("tree", "touch_price_mode_in_this_tree",
                                          "n_price_calls", "touch_counters")}, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
