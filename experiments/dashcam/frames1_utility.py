#!/usr/bin/env python3
"""StudyFRAMES1: what an extra frame per call is worth, as a function of delivery delay.

CPU only; no GPU, no model server, no inference. Pre-registered in `research/EXPERIMENTS.md`
(StudyFRAMES1) before anything was computed.

WHAT IS COMPARED. StudyD14b holds four committed arms on the same 0.25-s grid: 32BI and 4BI, at
N = 1 and N = 3 frames per call. For each arm the application's visible stream is StudyE9d's
`cloud_delivered`, that is calls on a fixed cadence and sample-and-hold of the newest delivered
score, and the metric is StudyE9c's challenge AP at horizons 0.5 / 1.0 / 1.5 s.

TWO PARAMETERIZATIONS, both reported, because they answer different questions.

  MATCHED TOTAL DELAY (primary). The hold shift is set to the SAME total for both N, so the only
  difference between the two columns is what the model saw. This isolates capability from cost
  and is what the policy's u_SH(cloud, d, m) needs: at a given delivered delay d, is m = 3 worth
  more than m = 1?

  EACH ARM AT ITS OWN MEASURED LATENCY (secondary). StudyE9b setting (ii) charges N = 3 its real
  payload: 1,057,532 B against 354,902 B at 13.6 Mbit/s, plus its own TTFT. The extra frames
  therefore arrive later, and this column says whether they pay for their own upload. This is
  StudyE9d's own parameterization (it adds delay ON TOP of each arm's base shift).

THE LIMITATION THE ROW PRE-REGISTERS. N = 3 in StudyD14b is three CONSECUTIVE frames at the
trace's own stride, so this study bounds rather than measures spec 7.9's merge rule, which merges
two calls that are a CADENCE apart. Section 4 of the report states what that does and does not
license, and what measurement would close it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (HERE, ROOT / "experiments/orchestration/sim",
          ROOT / "experiments/orchestration/baselines", ROOT / "experiments/lib"):
    sys.path.insert(0, str(p))

import d14b_split as SP                                   # noqa: E402
import metrics as M                                       # noqa: E402

OUT = ROOT / "results/dashcam/frames1"
STEP = 0.25
SETTING = "measured@25"
ARMS = (("32BI", 1), ("32BI", 3), ("4BI", 1), ("4BI", 3))
CADENCES_S = (0.5, 1.0)
PRIMARY_CADENCE_S = 0.5
TOTAL_DELAYS_S = tuple(round(0.25 * k, 2) for k in range(13))      # 0 .. 3.0 s, StudyE9d's grid
NB, SEED = 2000, 0


def arm_latency(ctx, model: str, n: int):
    """(latency, hold shift) under setting (ii), or (None, None) when no committed TTFT exists.

    StudyD7 / D7b measured the 4B at N = 1 only, so ('4BI', 3) has NO measured serving latency.
    Nothing is estimated for it: that arm appears in the matched-total-delay analysis, which needs
    no latency, and is reported as NOT AVAILABLE in the own-latency analysis.
    """
    import study_e9b_dense as B
    try:
        L = B.latencies(SETTING, model, n)[1]
    except KeyError:
        return None, None
    return float(L), int(B.shift_steps(ctx, L))


def delivered(ctx, model: str, n: int, cadence_s: float, shift_steps: int,
              clips: Sequence[str]) -> Dict[str, np.ndarray]:
    import study_e9d_delay as D
    mc = int(round(cadence_s / STEP))
    return {c: D.cloud_delivered(ctx["arrs"][(model, n)][c], ctx["meta"][c]["G"], mc,
                                 shift_steps) for c in clips}


def paired_gain(ch, a: Dict[str, np.ndarray], b: Dict[str, np.ndarray], pos: Sequence[str],
                neg: Sequence[str]) -> Dict[str, Any]:
    """AP(a) - AP(b) on the same resampled clips: StudyE9c's unit and seed."""
    import study_e9d_delay as D
    PA, NA = ch.crops(a)
    PB, NBd = ch.crops(b)
    rng = np.random.default_rng(SEED)
    draws = [(rng.integers(0, len(pos), len(pos)), rng.integers(0, len(neg), len(neg)))
             for _ in range(NB)]
    diffs = np.empty(NB)
    for i, (pi, ni) in enumerate(draws):
        va, vb = [], []
        for h in D.CHAL_H:
            sel = pi[ch.pmask[h][pi]]
            if not len(sel):
                continue
            y = np.r_[np.ones(len(sel)), np.zeros(len(ni))]
            va.append(D.ap_fast(y, np.r_[PA[h][sel], NA[h][ni]]))
            vb.append(D.ap_fast(y, np.r_[PB[h][sel], NBd[h][ni]]))
        diffs[i] = float(np.mean(va) - np.mean(vb))
    pa, pb = ch.point(a)["mAP"], ch.point(b)["mAP"]
    lo, hi = float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))
    return dict(gain=float(pa - pb), ci=[lo, hi], excludes_zero=bool(lo > 0 or hi < 0),
                mAP_N3=float(pa), mAP_N1=float(pb))


def main() -> int:
    from _provenance import stamp
    import study_e9b_dense as B
    OUT.mkdir(parents=True, exist_ok=True)
    ctx = B.build(step=STEP)
    s = SP.split()
    sides = {"DEV": s["dev"], "EVAL": s["eval"]}
    chs = {}
    for side in sides:
        M._ensure_sklearn_importable()
        import study_e9d_delay as D
        chs[side] = D.Challenge(SP.subset_ctx(ctx, side))

    res: Dict[str, Any] = dict(
        label=("StudyFRAMES1: challenge AP against delivery delay for 32BI and 4BI at N = 1 and "
               "N = 3, at MATCHED TOTAL DELAY (primary) and at each arm's own measured latency "
               "(secondary). CPU only; committed traces; no inference."),
        setting=SETTING, step_s=STEP, cadences_s=list(CADENCES_S),
        primary_cadence_s=PRIMARY_CADENCE_S, total_delays_s=list(TOTAL_DELAYS_S),
        split=dict(rule=s["rule"], n_dev=s["n_dev"], n_eval=s["n_eval"]),
        arms={}, matched_total_delay={}, own_latency={}, gain_vs_delay={})

    for (m, n) in ARMS:
        L, sh = arm_latency(ctx, m, n)
        res["arms"]["%s_N%d" % (m, n)] = dict(
            measured_latency_s=L, hold_shift_steps=sh,
            hold_shift_s=(sh * STEP if sh is not None else None),
            source=("StudyE9b setting (ii): RTT 0.044 s + StudyD4 frame bytes / 13.6 Mbit/s "
                    "uplink + StudyD7 / D7b TTFT at 25 % of peak load" if L is not None else
                    "NOT AVAILABLE: StudyD7 / D7b measured the 4B at N = 1 only, so this arm has "
                    "no committed serving latency and none is estimated here"))

    # ---- primary: matched total delay
    for side, clips in sides.items():
        ch = chs[side]
        sub = SP.subset_ctx(ctx, side)
        for cad in CADENCES_S:
            for d in TOTAL_DELAYS_S:
                sh = int(round(d / STEP))
                for (m, n) in ARMS:
                    st = delivered(ctx, m, n, cad, sh, clips)
                    pt = ch.point(st)
                    res["matched_total_delay"]["%s|%s_N%d@%s|D%.2f" % (side, m, n, cad, d)] = dict(
                        side=side, arm="%s_N%d" % (m, n), cadence_s=cad, total_delay_s=d,
                        challenge_mAP=float(pt["mAP"]),
                        challenge_ap={str(h): float(v) for h, v in pt.items() if h != "mAP"})
        # the gain from extra frames, at matched total delay, with a paired CI
        for tier in ("32BI", "4BI"):
            for d in TOTAL_DELAYS_S:
                sh = int(round(d / STEP))
                a = delivered(ctx, tier, 3, PRIMARY_CADENCE_S, sh, clips)
                b = delivered(ctx, tier, 1, PRIMARY_CADENCE_S, sh, clips)
                res["gain_vs_delay"]["%s|%s|D%.2f" % (side, tier, d)] = dict(
                    side=side, tier=tier, total_delay_s=d, cadence_s=PRIMARY_CADENCE_S,
                    **paired_gain(ch, a, b, sub["pos"], sub["neg"]))

    # ---- secondary: each arm at its own measured latency, plus StudyE9d's added delay
    for side, clips in sides.items():
        ch = chs[side]
        for cad in CADENCES_S:
            for (m, n) in ARMS:
                base = res["arms"]["%s_N%d" % (m, n)]["hold_shift_steps"]
                if base is None:
                    continue
                for add in TOTAL_DELAYS_S:
                    sh = base + int(round(add / STEP))
                    st = delivered(ctx, m, n, cad, sh, clips)
                    pt = ch.point(st)
                    res["own_latency"]["%s|%s_N%d@%s|add%.2f" % (side, m, n, cad, add)] = dict(
                        side=side, arm="%s_N%d" % (m, n), cadence_s=cad, added_delay_s=add,
                        base_hold_shift_s=base * STEP, total_hold_shift_s=sh * STEP,
                        challenge_mAP=float(pt["mAP"]))
        # does N = 3 pay for its own upload? compare each arm at its OWN latency, no added delay
        for tier in ("32BI", "4BI"):
            if res["arms"]["%s_N3" % tier]["hold_shift_steps"] is None:
                res["own_latency"]["%s|%s|N3_minus_N1_at_own_latency" % (side, tier)] = dict(
                    side=side, tier=tier, available=False,
                    reason=("no committed serving latency for %s N = 3 (StudyD7 / D7b measured "
                            "the 4B at N = 1 only); nothing is estimated" % tier))
                continue
            a = delivered(ctx, tier, 3, PRIMARY_CADENCE_S,
                          res["arms"]["%s_N3" % tier]["hold_shift_steps"], clips)
            b = delivered(ctx, tier, 1, PRIMARY_CADENCE_S,
                          res["arms"]["%s_N1" % tier]["hold_shift_steps"], clips)
            sub = SP.subset_ctx(ctx, side)
            res["own_latency"]["%s|%s|N3_minus_N1_at_own_latency" % (side, tier)] = dict(
                side=side, tier=tier, cadence_s=PRIMARY_CADENCE_S,
                n3_hold_shift_s=res["arms"]["%s_N3" % tier]["hold_shift_steps"] * STEP,
                n1_hold_shift_s=res["arms"]["%s_N1" % tier]["hold_shift_steps"] * STEP,
                **paired_gain(ch, a, b, sub["pos"], sub["neg"]))

    res["_provenance"] = stamp(script="frames1_utility.py", model=None, device="cpu",
                               n=len(ctx["clips"]), args=None)
    (OUT / "frames1_results.json").write_text(json.dumps(res, indent=1, default=float))
    print("arms:")
    for k, v in res["arms"].items():
        if v["measured_latency_s"] is None:
            print("  %-10s NO COMMITTED LATENCY (matched-delay analysis only)" % k)
        else:
            print("  %-10s latency %.4f s -> hold shift %d steps (%.2f s)"
                  % (k, v["measured_latency_s"], v["hold_shift_steps"], v["hold_shift_s"]))
    for side in ("DEV", "EVAL"):
        print("%s, matched total delay, cadence %.1f s:" % (side, PRIMARY_CADENCE_S))
        for tier in ("32BI", "4BI"):
            row = []
            for d in (0.0, 0.5, 1.0, 1.5, 2.0, 3.0):
                g = res["gain_vs_delay"]["%s|%s|D%.2f" % (side, tier, d)]
                row.append("d=%.1f %+.4f%s" % (d, g["gain"], "*" if g["excludes_zero"] else ""))
            print("  %s N3 minus N1: %s" % (tier, "  ".join(row)))
            o = res["own_latency"]["%s|%s|N3_minus_N1_at_own_latency" % (side, tier)]
            if not o.get("available", True):
                print("     at own latency: NOT AVAILABLE (%s)" % o["reason"])
            else:
                print("     at own latency (%.2f s against %.2f s): %+.4f [%+.4f, %+.4f]%s"
                      % (o["n3_hold_shift_s"], o["n1_hold_shift_s"], o["gain"], o["ci"][0],
                         o["ci"][1], " EXCLUDES ZERO" if o["excludes_zero"] else ""))
    print("wrote", OUT / "frames1_results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
