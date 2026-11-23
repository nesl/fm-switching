#!/usr/bin/env python3
"""D206: ONE DEFICIT SOURCE. The guard test plus the c1 equivalence proof.

TWO THINGS ARE PROVED HERE AND THEY ARE DIFFERENT.

  THE GUARD (D206 item 2). No registered arm's live path constructs `cf_objective.DeficitCounters`.
  This is what keeps "superseded, no live path" TRUE AS THE TREE CHANGES instead of resting on one
  day's grep. Every registered arm is CONSTRUCTED, its planner engine is built where it has one,
  and the engine's weight source is inspected. A new arm that defaults back to the superseded
  counter fails here rather than three days later in a plausible null.

  THE EQUIVALENCE (D206 item c1, the load-bearing proof now that the 54-arm sweep is cut). The
  declared constant returns EXACTLY what the unfed counter returned at EVERY ONE of the five read
  sites, so every arm moved from one to the other is decision-identical by arithmetic rather than
  by digest. The five sites, enumerated and each exercised:

    1  cf_planner.py plan_request   `w = self.counters.weight(device_id)`
    2  cf_planner.py plan_request   `counters=self.counters` into cf_objective.harm_to_others
    3  cf_planner.py plan_state     `w = self.counters.weight(device_id)`
    4  cf_planner.py plan_sync      `w = self.counters.weight(device_id)`
    5  arms_v6state.py              `counters=cf.counters` into harm_warm_from_queue_delay

  Sites 1, 3 and 4 are the same call, so the test asserts `weight` is EXACTLY equal (`==`, not
  `isclose`) over a device set that includes every roster prefix AND the unresolvable cases. Sites
  2 and 5 pass the OBJECT, so the test drives both functions with each source and asserts the
  returned harm is exactly equal, which is strictly stronger than comparing `weight`: it is the
  only form that covers the `w = counters.weight(...) if counters else row.weight` OVERRIDE inside
  `harm_to_others` and `harm_warm_from_queue_delay`, where passing an object DISCARDS the row's
  own weight. Each equality carries a POSITIVE CONTROL with a w = 2.0 source, because an equality
  that would also hold between two broken objects proves nothing.

RUN: python -I experiments/orchestration/live2/d206_guard_proofs.py
Exit code is asserted; every check prints PASS or FAIL with its own name.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
L = HERE.parent
for _p in (str(L), str(L / "fleet"), str(L / "v5"), str(L / "hybrid"),
           str(L.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cf_cost as CC                                                           # noqa: E402
import cf_objective as CO                                                      # noqa: E402

FAILED = []
N = [0]


def check(name, cond, detail=""):
    N[0] += 1
    ok = bool(cond)
    if not ok:
        FAILED.append(name)
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, ("  " + detail) if detail else ""))


# every roster prefix, PLUS the ids a resolver cannot resolve. An equivalence proved only on
# well-formed ids would miss exactly the rows that take a fallback.
DEVICES = ["robo000", "robo001", "robo005", "dash000", "dash005", "asst000", "asst002",
           "", "unknown999", "robo001|s000|xyz_start_0.0_end_1.0", "None"]


class _W2:
    """A w = 2.0 source, for the positive controls."""

    IS_DECLARED_CONSTANT = False

    def weight(self, d):
        return 2.0

    def shortfall(self, d):
        return 0.0


def main() -> int:
    unfed = CO.DeficitCounters()          # the superseded object, AS IT WAS ON THE LIVE PATH
    const = CO.NoPlannerDeficitFeed(rung="test")

    check("DeficitCounters is marked SUPERSEDED with NO LIVE PATH",
          "SUPERSEDED" in (CO.DeficitCounters.__doc__ or "")
          and "NO LIVE PATH" in (CO.DeficitCounters.__doc__ or "").upper())
    check("NoPlannerDeficitFeed declares itself a constant",
          getattr(CO.NoPlannerDeficitFeed, "IS_DECLARED_CONSTANT", False) is True)
    check("NoPlannerDeficitFeed carries a written declaration",
          "no deficit feed in the state planner" in const.as_dict()["declaration"])

    diffs = [(d, unfed.weight(d), const.weight(d))
             for d in DEVICES if unfed.weight(d) != const.weight(d)]
    check("sites 1/3/4 weight() EXACTLY equal over %d devices incl. unresolvable" % len(DEVICES),
          not diffs, "max abs diff 0.0" if not diffs else repr(diffs[:3]))
    check("and the shared value is exactly 1.0",
          all(const.weight(d) == 1.0 for d in DEVICES))
    check("shortfall() exactly equal (read by the plan_state trace)",
          all(unfed.shortfall(d) == const.shortfall(d) for d in DEVICES))
    check("starving() equal (reader 5, D149 (3))",
          all(unfed.starving(d) == const.starving(d) for d in DEVICES))

    def plan(delay):
        return [CC.PendingRequest(req_id="r%d" % i, device_id=DEVICES[i % 7],
                                  start_s=float(i) + delay, tokens=2000 + 100 * i,
                                  cached_tokens=0, deadline_abs_s=float(i) + 3.0,
                                  accuracy=0.25, weight=7.0,   # a WRONG row weight on purpose
                                  kind="robot", question_id=None, episode_frames=None)
                for i in range(6)]

    model = CC.load_gate_model()
    res = CC.load_residuals()
    before = CC.plan_queue(model, res, plan(0.0), now_s=0.0, exact_until_s=1e9,
                           decision_kind="request", coarse_overlap_forecast=0.0)
    after = CC.plan_queue(model, res, plan(0.6), now_s=0.0, exact_until_s=1e9,
                          decision_kind="request", coarse_overlap_forecast=0.0)
    h_unfed = CO.harm_to_others(before, after, candidate_req_id="r0", counters=unfed)
    h_const = CO.harm_to_others(before, after, candidate_req_id="r0", counters=const)
    h_two = CO.harm_to_others(before, after, candidate_req_id="r0", counters=_W2())
    check("site 2 harm_to_others total EXACTLY equal",
          h_unfed.total == h_const.total,
          "%r vs %r over %d / %d rows" % (h_unfed.total, h_const.total,
                                          h_unfed.n_affected, h_const.n_affected))
    check("site 2 every harm ROW exactly equal (the weight override)",
          [dict(r) for r in h_unfed.rows] == [dict(r) for r in h_const.rows])
    check("POSITIVE CONTROL: a w = 2.0 source DOES move harm_to_others",
          h_two.total != h_unfed.total,
          "w=2 gives %r against %r; if this fails the equality above is vacuous"
          % (h_two.total, h_unfed.total))

    others = [{"req_id": "o%d" % i, "device_id": DEVICES[i % 7], "engine_s": 0.4 + 0.05 * i,
               "slack_s": 0.9, "p_device_on_time": 1.0, "weight": 7.0} for i in range(5)]
    kw = dict(p_on_time=(lambda eng, slack: CC.p_on_time(res, eng, slack)),
              acc_cloud=1.0, acc_device=0.0)
    w_unfed = CO.harm_warm_from_queue_delay(3000, others, counters=unfed, **kw)
    w_const = CO.harm_warm_from_queue_delay(3000, others, counters=const, **kw)
    w_two = CO.harm_warm_from_queue_delay(3000, others, counters=_W2(), **kw)
    check("site 5 harm_warm_from_queue_delay total EXACTLY equal",
          w_unfed.total == w_const.total, "%r vs %r" % (w_unfed.total, w_const.total))
    check("site 5 every row exactly equal (the weight override)",
          [dict(r) for r in w_unfed.rows] == [dict(r) for r in w_const.rows])
    check("POSITIVE CONTROL: a w = 2.0 source DOES move harm_warm",
          w_two.total != w_unfed.total, "w=2 gives %r" % (w_two.total,))

    import cf_planner as CP
    try:
        CP.Counterfactual(dry=True, dry_margin=1.0)
        check("cf_planner RAISES when no weight source is declared", False, "it did not raise")
    except CP.WeightSourceUndeclared:
        check("cf_planner RAISES when no weight source is declared", True)
    except Exception as e:                                                 # noqa: BLE001
        check("cf_planner RAISES when no weight source is declared", False, repr(e)[:120])

    import arms as A
    bad, built, no_engine, errs, sources = [], 0, 0, {}, {}
    for name in sorted(A.ARMS):
        try:
            arm = A.ARMS[name]()
        except Exception as e:                                             # noqa: BLE001
            errs[name] = type(e).__name__
            continue
        built += 1
        eng = getattr(arm, "_cf_engine", None)
        if not callable(eng):
            no_engine += 1
            continue
        try:
            cf = eng()
        except Exception as e:                                             # noqa: BLE001
            errs[name] = "engine: " + type(e).__name__
            continue
        src = type(cf.counters).__name__
        sources[src] = sources.get(src, 0) + 1
        if isinstance(cf.counters, CO.DeficitCounters):
            bad.append(name)
    check("GUARD: no registered arm's live path constructs DeficitCounters",
          not bad, "built %d, %d have no engine, sources %r, offenders %r"
          % (built, no_engine, sources, bad[:5]))
    check("GUARD: the only live sources are the declared constant and the rung-4 live feed",
          set(sources) <= {"NoPlannerDeficitFeed", "PlannerDeficitWeights"}, repr(sources))
    check("GUARD: at least one arm uses the rung-4 LIVE source, so the guard is not vacuous",
          sources.get("PlannerDeficitWeights", 0) > 0, repr(sources))
    check("GUARD: construction errors are only the by-design refusal",
          set(errs) <= {"covex-v6-cf-pd"}, repr(errs))

    print("\n%d of %d checks passed" % (N[0] - len(FAILED), N[0]))
    if FAILED:
        print("FAILED: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
