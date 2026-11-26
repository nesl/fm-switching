#!/usr/bin/env python3
"""q5 unit proofs. CPU only."""
from __future__ import annotations
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

HERE = Path(__file__).resolve().parent
for p in (HERE / "hybrid", HERE, HERE / "fleet", HERE / "v5", HERE / "tests", HERE.parent / "baselines", HERE.parent / "sim"):
    sys.path.insert(0, str(p))
import arms as A                                                               # noqa: E402
import q5_queue_aware_holdback as Q5                                           # noqa: E402

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
    R3, Q = "covex-v6-fair-final", "covex-v6-fair-final-q5"
    for n in (R3, "covex-v6-fair-final-q", "covex-v6-fair-final-q2m", "covex-v6-fair-final-q4"):
        check("q5 OFF on %s" % n, Q5.arm_enables(A.make_arm(n)) is False)
    a = A.make_arm(Q)
    import d249_queue_visibility as QV
    import d261_margin_scope as MS
    import q4_avoided_rebuild as Q4
    check("q5 ON; D249, q2, q2m, q4 all OFF", Q5.arm_enables(a) and not QV.arm_enables(a)
          and not QV.q2_arm_enables(a) and not MS.q2m_arm_enables(a) and not Q4.arm_enables(a))
    check("q5 margin is rung 3's 0.65824 (no override)", abs(a._cf_engine()._margin().value - 0.65824) < 1e-9)
    check("q5 and rung 3 share a class", type(a) is type(A.make_arm(R3)))
    r = A.make_arm(R3)
    k = type(r)
    setattr(k, Q5.Q5_SWITCH, True)
    try:
        ok = raises(lambda: Q5.arm_enables(r), Q5.Q5SwitchError)
    finally:
        delattr(k, Q5.Q5_SWITCH)
    check("class attribute raises", ok)
    b = A.make_arm(R3)
    object.__setattr__(b, Q5.Q5_SWITCH, 1)
    check("non-bool raises", raises(lambda: Q5.arm_enables(b), Q5.Q5SwitchError))
    # committed coefficient, read from the committed JSON and nowhere else
    raw = json.loads((HERE.parents[2] / Q5.STEP_MODEL_REL).read_text())
    c = raw["coef"]
    check("step model is the committed StudyENG1 file", Q5.step_model()["coef"] == c and raw["n"] == 5974)
    e0 = Q5.extra_step_ms(1000, 0)
    want = c["per_tok_ms"] * 1000 + c["per_tok_above_512_ms"] * 488 + c["per_prefill_req_ms"]
    check("extra step ms, 1000 tokens, no ctx, by hand", abs(e0 - want) < 1e-9, "%.4f" % e0)
    check("extra step ms rises with ctx (attention over cached context)", Q5.extra_step_ms(1000, 20000) > e0)
    s1, s2, s3 = (Q5.interference_s(u, 10000) for u in (500, 5000, 20000))
    check("interference rises with the held-back tokens", 0 < s1 < s2 < s3, "%.4f %.4f %.4f s" % (s1, s2, s3))
    check("interference 20,000 tokens = 3 chunks (8192, 8192, 3616)",
          abs(Q5.interference_s(20000, 0) - (2 * Q5.extra_step_ms(8192, 0) + Q5.extra_step_ms(3616, 0)) / 1000) > 0)
    chunks = [8192, 8192, 3616]
    ctx = 0
    tot = 0.0
    for n in chunks:
        tot += Q5.extra_step_ms(n, ctx)
        ctx += n
    check("chunked sum with growing context matches", abs(Q5.interference_s(20000, 0) - tot / 1000) < 1e-12)
    # the in-flight harm term, with stubbed rows
    a = A.make_arm(Q)
    from interface import InFlightWork
    sdev = {"s0": "robo000"}
    a._rules._roster = {"session_device": sdev, "devices": {"robo000": {"type": "robot"}}}
    mk = lambda i, dev, slack: InFlightWork(request_id="r%d" % i, device_id=dev, qtype="alert", kind="monitor",
                                            uncached_tokens=400, slack_s=slack, has_deadline=True)
    obs = NS(cloud=NS(in_flight_work=(mk(1, "dash000", 0.30), mk(2, "dash001", 0.35), mk(3, "robo000", 0.05))))
    check("D249 off: the D249 row builder still returns [] by default", a._d249_rows(obs, "s0") == [])
    rows = a._d249_rows(obs, "s0", force=True)
    check("force rows: other devices only (own device excluded)", [r["device_id"] for r in rows] == ["dash000", "dash001"])
    h_small = a._q5_inflight_harm(obs, "s0", 500, 5000)
    h_big = a._q5_inflight_harm(obs, "s0", 20000, 15000)
    check("in-flight term non-zero and rises with the held-back prefill", 0.0 <= h_small < h_big, "%.4f %.4f" % (h_small, h_big))
    obs2 = NS(cloud=NS(in_flight_work=(mk(1, "dash000", 30.0), mk(2, "dash001", 30.0))))
    check("rows with ample slack: term 0 (not a blanket brake)", a._q5_inflight_harm(obs2, "s0", 20000, 15000) == 0.0)
    obs3 = NS(cloud=NS(in_flight_work=()))
    check("no rows in flight: term 0, counted", a._q5_inflight_harm(obs3, "s0", 20000, 15000) == 0.0
          and a.stats["q5_inflight_no_rows"] == 1)
    object.__setattr__(a, Q5.FORCE_ZERO_ATTR, True)
    check("force-zero hook returns 0.0", a._q5_inflight_harm(obs, "s0", 20000, 15000) == 0.0)
    print("FAILS:", FAILS)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
