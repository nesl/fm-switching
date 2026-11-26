#!/usr/bin/env python3
"""q4 unit proofs: the estimator, the credit, the switch, and the READ of the credit by the decision.
CPU only. Run: python q4_avoided_rebuild_proofs.py"""
from __future__ import annotations
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE / "hybrid", HERE, HERE / "fleet", HERE / "v5", HERE / "tests", HERE.parent / "baselines", HERE.parent / "sim"):
    sys.path.insert(0, str(p))

import arms as A                                                               # noqa: E402
import q4_avoided_rebuild as Q4                                                # noqa: E402

Q4N, Q2M, Q2, Q, R3 = ("covex-v6-fair-final-q4", "covex-v6-fair-final-q2m", "covex-v6-fair-final-q2",
                       "covex-v6-fair-final-q", "covex-v6-fair-final")
FAILS = []


def check(name, ok, detail=""):
    print("%s %s %s" % ("PASS" if ok else "FAIL", name, detail))
    if not ok:
        FAILS.append(name)


def raises(fn, exc):
    try:
        fn()
    except exc:
        return True
    return False


class _Cand:
    def __init__(self, name, value, scored=True):
        self.name, self.value, self.scored = name, value, scored


def main():
    # ---- estimator
    check("bins: 6", Q4.N_BINS == 6 and Q4.EDGES_S == (5.0, 15.0, 30.0, 60.0, 120.0))
    check("bin edges", [Q4.bin_of(g) for g in (0, 4.99, 5, 14.9, 15, 29.9, 30, 59.9, 60, 119.9, 120, 1e6)]
          == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5])
    e = Q4.ColdEstimator()
    check("prior mean 0.05 in every bin", all(abs(e.p_cold_bin(i) - 0.05) < 1e-12 for i in range(6)))
    b = e.update(20.0, True)
    check("update lands in bin 2", b == 2 and e.n[2] == 1 and e.cold[2] == 1)
    check("posterior after 1 cold in bin 2 = (0.1+1)/(2+1)", abs(e.p_cold_bin(2) - 1.1 / 3.0) < 1e-12)
    check("other bins untouched", all(abs(e.p_cold_bin(i) - 0.05) < 1e-12 for i in (0, 1, 3, 4, 5)))
    e2 = Q4.ColdEstimator()
    for g, k in ((2, 0), (10, 1), (20, 3), (45, 6), (90, 9), (200, 10)):          # cold fraction rises with gap
        for i in range(10):
            e2.update(g, i < k)
    pc = [e2.p_cold_bin(i) for i in range(6)]
    check("monotone rise with idle gap on rising data", all(pc[i] < pc[i + 1] for i in range(5)),
          repr([round(x, 3) for x in pc]))
    e3 = Q4.ColdEstimator()
    for _ in range(200):
        e3.update(7.0, False)
    check("posterior converges to the data (0 cold of 200)", e3.p_cold_bin(1) < 0.001)
    # ---- switch
    for n in (R3, Q, Q2, Q2M):
        check("switch OFF on %s" % n, Q4.arm_enables(A.make_arm(n)) is False)
    a = A.make_arm(Q4N)
    check("switch ON on q4 and q2m ON", Q4.arm_enables(a) is True and a._q4_on() is True)
    check("q4 margin is q2m's 0.65824", abs(a._cf_engine()._margin().value - 0.65824) < 1e-9)
    r = A.make_arm(R3)
    k = type(r)
    setattr(k, Q4.Q4_SWITCH, True)
    try:
        ok = raises(lambda: Q4.arm_enables(r), Q4.Q4SwitchError)
    finally:
        delattr(k, Q4.Q4_SWITCH)
    check("class attribute raises", ok)
    b2 = A.make_arm(Q2M)
    object.__setattr__(b2, Q4.Q4_SWITCH, 1)
    check("non-bool raises", raises(lambda: Q4.arm_enables(b2), Q4.Q4SwitchError))
    b3 = A.make_arm(Q2)
    object.__setattr__(b3, Q4.Q4_SWITCH, True)
    check("on without q2m raises", raises(lambda: Q4.arm_enables(b3), Q4.Q4SwitchError))
    # ---- observe: cold rule, gap definition, no-evidence
    a = A.make_arm(Q4N)
    a._rules._roster = {"devices": {"robo000": {"type": "robot"}, "dash000": {"type": "dashcam"}}}
    rec = lambda **kw: dict(dict(kind="recall", device_id="robo000", session_id="s0", t_submit=100.0,
                                 t_done=101.0, prompt_tokens=1000, cached_tokens=900), **kw)
    Q4.observe(a, rec(t_submit=10.0, t_done=11.0))
    check("first request: no gap, no update", a.stats["q4_obs_no_previous_request"] == 1 and sum(Q4.state_of(a).est.n) == 0)
    Q4.observe(a, rec(t_submit=31.0, t_done=32.0, cached_tokens=900))             # gap 20 s, warm
    Q4.observe(a, rec(t_submit=62.0, t_done=63.0, cached_tokens=499))             # gap 30 s, cold (0.499)
    Q4.observe(a, rec(t_submit=93.0, t_done=94.0, cached_tokens=500))             # gap 30 s, NOT cold (0.5)
    st = Q4.state_of(a).est
    check("gap = submit minus previous DONE; bins", st.n[2] == 1 and st.n[3] == 2, repr(st.n))
    check("cold iff cached/prompt < 0.5 (499 cold, 500 not)", st.cold[3] == 1 and st.cold[2] == 0, repr(st.cold))
    Q4.observe(a, rec(t_submit=200.0, t_done=201.0, cached_tokens=None))
    check("no cached_tokens is no evidence, counted", a.stats["q4_obs_no_cached_evidence"] == 1 and sum(st.n) == 3)
    Q4.observe(a, rec(device_id="dash000", t_submit=300.0, t_done=301.0))
    check("non-robot response not learned from", sum(st.n) == 3)
    Q4.observe(a, rec(kind="piece", t_submit=400.0, t_done=401.0))
    check("non-recall kind not learned from, but advances last_done", sum(st.n) == 3 and Q4.state_of(a).last_done["s0"] == 401.0)
    # ---- credit arithmetic: credit = P(cold|gap) x harm
    a = A.make_arm(Q4N)
    for i in range(10):
        Q4.state_of(a).est.update(40.0, i < 5)                                       # bin 3: 5/10 cold
    Q4.state_of(a).last_done["s0"] = 100.0
    seen = {}
    a._harm_warm = lambda obs, sid, u, include_inflight=True: seen.update(u=u) or 0.8

    class _O:
        now_s = 140.0
    c = a._q4_credit(_O(), "s0", 12345)
    want = (0.1 + 5) / (2 + 10) * 0.8
    check("credit = P(cold|gap 40s) x harm", abs(c - want) < 1e-12 and seen["u"] == 12345, "%r %r" % (c, want))
    _O.now_s = 100.0 + 200.0
    c2 = a._q4_credit(_O(), "s0", 12345)
    check("long gap, unseen bin falls back to the prior (0.05 x harm)", abs(c2 - 0.05 * 0.8) < 1e-12)
    check("no previous request: credit 0, counted", a._q4_credit(_O(), "nobody", 1) == 0.0 and a.stats["q4_credit_no_gap"] == 1)
    object.__setattr__(a, Q4.FORCE_ZERO_ATTR, True)
    _O.now_s = 140.0
    check("force-zero hook returns 0.0", a._q4_credit(_O(), "s0", 12345) == 0.0)
    # ---- the decision READS the credit (cf_planner.plan_state)
    cf = A.make_arm(Q4N)._cf_engine()
    kw = dict(decision_id="x", device_id="robo000", now_s=10.0, p_question=0.5, next_question_s=20.0,
              p_on_time_warm=0.9, p_on_time_cold=0.8, harm_warm=0.0, harm_touch=0.0,
              warm_expressible=False, host_warm=False)
    d0 = cf.plan_state(**kw)
    d1 = cf.plan_state(touch_credit=0.0, **kw)
    check("credit 0.0 leaves the TOUCH value identical", d0.chosen == d1.chosen == "KEEP"
          and [c.value for c in d0.candidates] == [c.value for c in d1.candidates])
    m = d0.margin_effective
    d2 = cf.plan_state(touch_credit=m * 1.01, **kw)
    t0 = next(c for c in d0.candidates if c.name == "TOUCH").value
    t2 = next(c for c in d2.candidates if c.name == "TOUCH").value
    check("credit is ADDED to the TOUCH value", abs((t2 - t0) - m * 1.01) < 1e-12)
    check("credit above the margin flips KEEP to TOUCH (the READ)", d2.chosen == "TOUCH" and d2.deviated)
    d3 = cf.plan_state(touch_credit=m * 0.5, **kw)
    check("credit below the margin does not", d3.chosen == "KEEP")
    check("would_choose_without removes the credit",
          Q4.would_choose_without(d2.candidates, m * 1.01, m) == "KEEP"
          and Q4.would_choose_without(d2.candidates, 0.0, m) == "TOUCH")
    print("FAILS:", FAILS)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
