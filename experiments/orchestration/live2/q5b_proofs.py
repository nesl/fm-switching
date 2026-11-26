#!/usr/bin/env python3
"""q5b unit proofs. CPU only."""
from __future__ import annotations
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
    for n in ("covex-v6-fair-final", "covex-v6-fair-final-q5"):
        check("q5b OFF on %s" % n, Q5.q5b_arm_enables(A.make_arm(n)) is False)
    a = A.make_arm("covex-v6-fair-final-q5b")
    check("q5b ON and q5 ON", Q5.q5b_arm_enables(a) and Q5.arm_enables(a) and a._q5b_on())
    r = A.make_arm("covex-v6-fair-final-q5")
    k = type(r)
    setattr(k, Q5.Q5B_SWITCH, True)
    try:
        ok = raises(lambda: Q5.q5b_arm_enables(r), Q5.Q5bSwitchError)
    finally:
        delattr(k, Q5.Q5B_SWITCH)
    check("class attribute raises", ok)
    b = A.make_arm("covex-v6-fair-final-q5")
    object.__setattr__(b, Q5.Q5B_SWITCH, 1)
    check("non-bool raises", raises(lambda: Q5.q5b_arm_enables(b), Q5.Q5bSwitchError))
    c = A.make_arm("covex-v6-fair-final")
    object.__setattr__(c, Q5.Q5B_SWITCH, True)
    check("on without q5 raises", raises(lambda: Q5.q5b_arm_enables(c), Q5.Q5bSwitchError))
    # committed-model numbers at the held sessions' built context (about 1,200 tokens, the q5 cell's): 1,024 -> 0.092, 8,192 -> 1.106, larger shortfalls capped at one chunk
    got = {u: Q5.interference_s(Q5.released_unit_tokens(u, None), 1200) for u in (1024, 8192, 17000, 25000)}
    check("slice None: 1,024 / 8,192 / 17,000 / 25,000 -> 0.092 / 1.106 / 1.106 / 1.106 s",
          abs(got[1024] - 0.092) < 0.0006 and all(abs(got[u] - 1.106) < 0.0006 for u in (8192, 17000, 25000)),
          repr({k: round(v, 4) for k, v in got.items()}))
    check("slice 1,024 (the arm's release unit): a 17,000 shortfall prices ONE 1,024 piece",
          Q5.released_unit_tokens(17000, 1024) == 1024 and Q5.released_unit_tokens(300, 1024) == 300
          and abs(Q5.interference_s(Q5.released_unit_tokens(17000, 1024), 1200) - got[1024]) < 1e-12)
    check("q5 (whole shortfall) for 17,000 over 1,200 ctx is the 2.416 s the diagnosis names",
          abs(Q5.interference_s(17000, 1200) - 2.416) < 0.002, "%.4f" % Q5.interference_s(17000, 1200))
    # the term itself, with stubbed rows
    from interface import InFlightWork
    a._rules._roster = {"session_device": {"s0": "robo000"}, "devices": {"robo000": {"type": "robot"}}}
    mk = lambda i, dev, slack: InFlightWork(request_id="r%d" % i, device_id=dev, qtype="alert", kind="monitor",
                                            uncached_tokens=400, slack_s=slack, has_deadline=True)
    obs = NS(cloud=NS(in_flight_work=(mk(1, "dash000", 0.40), mk(2, "dash001", 0.45))))
    h_piece = a._q5_inflight_harm(obs, "s0", Q5.released_unit_tokens(17000, 1024), 1200)
    h_whole = a._q5_inflight_harm(obs, "s0", 17000, 1200)
    check("in-flight term: released piece < whole shortfall on the same rows", 0.0 <= h_piece < h_whole,
          "%.4f %.4f" % (h_piece, h_whole))
    print("FAILS:", FAILS)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
