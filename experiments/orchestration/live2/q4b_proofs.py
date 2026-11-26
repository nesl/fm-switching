#!/usr/bin/env python3
"""q4b unit proofs (D290 iteration 2). CPU only."""
from __future__ import annotations
import sys
from pathlib import Path
from types import SimpleNamespace as NS

HERE = Path(__file__).resolve().parent
for p in (HERE / "hybrid", HERE, HERE / "fleet", HERE / "v5", HERE / "tests", HERE.parent / "baselines", HERE.parent / "sim"):
    sys.path.insert(0, str(p))
import arms as A                                                               # noqa: E402
import q4_avoided_rebuild as Q4                                                # noqa: E402

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


def main():
    for n in ("covex-v6-fair-final", "covex-v6-fair-final-q2m", "covex-v6-fair-final-q4"):
        check("q4b OFF on %s" % n, Q4.q4b_arm_enables(A.make_arm(n)) is False)
    a = A.make_arm("covex-v6-fair-final-q4b")
    check("q4b ON and q4 ON on q4b", Q4.q4b_arm_enables(a) and Q4.arm_enables(a) and a._q4b_on())
    r = A.make_arm("covex-v6-fair-final-q4")
    k = type(r)
    setattr(k, Q4.Q4B_SWITCH, True)
    try:
        ok = raises(lambda: Q4.q4b_arm_enables(r), Q4.Q4bSwitchError)
    finally:
        delattr(k, Q4.Q4B_SWITCH)
    check("class attribute raises", ok)
    b = A.make_arm("covex-v6-fair-final-q4")
    object.__setattr__(b, Q4.Q4B_SWITCH, 1)
    check("non-bool raises", raises(lambda: Q4.q4b_arm_enables(b), Q4.Q4bSwitchError))
    c = A.make_arm("covex-v6-fair-final-q2m")
    object.__setattr__(c, Q4.Q4B_SWITCH, True)
    check("on without q4 raises", raises(lambda: Q4.q4b_arm_enables(c), Q4.Q4bSwitchError))
    # credit does not read the current queue
    a = A.make_arm("covex-v6-fair-final-q4b")
    for i in range(10):
        Q4.state_of(a).est.update(60.0, i < 6)                                  # bin 4: 6/10 cold
        Q4.state_of(a).est.update(20.0, i < 1)                                  # bin 2: 1/10 cold
    Q4.state_of(a).last_done["s0"] = 100.0
    O = NS(now_s=110.0)
    a._harm_warm = lambda obs, sid, u, include_inflight=True: 0.8
    check("no arrival yet: credit 0, counted", a._q4_credit(O, "s0", 9999, horizon_s=0.0) == 0.0
          and a.stats["q4b_credit_no_arrival"] == 1)
    Q4.arrivals_of(a).add("q1", 0.8, 100)
    Q4.arrivals_of(a).add("q2", 0.4, 300)
    check("arrivals are a running mean (0.6 harm, 200 tokens), once per id",
          not Q4.arrivals_of(a).add("q1", 9.0, 9) and abs(Q4.arrivals_of(a).mean_harm() - 0.6) < 1e-12
          and Q4.arrivals_of(a).mean_tokens() == 200)
    outs = []
    for h in (0.0, 0.1, 5.0, 50.0):                                              # vary the CURRENT queue's harm
        a._harm_warm = lambda obs, sid, u, include_inflight=True, h=h: h
        outs.append(a._q4_credit(O, "s0", 9999, horizon_s=0.0))
    check("q4b credit unchanged when the current queued rows are varied", len(set(outs)) == 1 and outs[0] > 0, repr(outs))
    q4 = A.make_arm("covex-v6-fair-final-q4")
    for i in range(10):
        Q4.state_of(q4).est.update(10.0, i < 5)
    Q4.state_of(q4).last_done["s0"] = 100.0
    o4 = []
    for h in (0.0, 0.1, 5.0):
        q4._harm_warm = lambda obs, sid, u, include_inflight=True, h=h: h
        o4.append(q4._q4_credit(O, "s0", 9999))
    check("contrast: q4 credit DOES grow with the current queue", o4[0] < o4[1] < o4[2], repr(o4))
    # predicted gap: gap so far 10 s (bin 1, prior 0.05), horizon 50 s -> gap 60 s (bin 4)
    a._harm_warm = lambda *x, **k: 0.0
    c0 = a._q4_credit(O, "s0", 1, horizon_s=0.0)
    c50 = a._q4_credit(O, "s0", 1, horizon_s=50.0)
    pb4 = (0.1 + 6) / 12.0
    check("P(cold) read at gap-so-far + expected time to next question", abs(c50 - pb4 * 0.6) < 1e-9
          and abs(c0 - 0.05 * 0.6) < 1e-9, "%r %r" % (c0, c50))
    # arrival observer: robots only, once per query id
    a2 = A.make_arm("covex-v6-fair-final-q4b")
    a2._rules._roster = {"devices": {"r0": {"type": "robot"}, "d0": {"type": "dashcam"}},
                         "session_device": {"sr": "r0", "sd": "d0"}}
    a2._harm_warm = lambda obs, sid, u, include_inflight=True: 0.5
    a2._d249_tok_sum = lambda obs: 700
    ob = NS(recall=[NS(query_id="a", session_id="sr"), NS(query_id="b", session_id="sd")])
    a2._q4b_observe_arrivals(ob, {"sr": 1000}, {})
    a2._q4b_observe_arrivals(ob, {"sr": 1000}, {})
    ar = Q4.arrivals_of(a2)
    check("arrival observer: robot only, once per id", ar.n == 1 and ar.mean_tokens() == 700 and ar.mean_harm() == 0.5)
    print("FAILS:", FAILS)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
