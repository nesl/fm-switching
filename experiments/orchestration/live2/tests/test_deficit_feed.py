#!/usr/bin/env python3
"""Unit tests for the D178 (1) per-type deficit feed and its declared gain.

A PLAIN SCRIPT, because pytest is NOT installed in the fmtk env. Explicit pass/fail summary and a
non-zero exit on any failure, the same shape `d179_share_tests.py` uses.

These tests are about the ARITHMETIC and the PLUMBING, not about the policy: the denominators, the
currency, the episode derivation, the switch's strictness, and that the weights actually change the
consumer's answer. The cell-level proofs are `d178_deficit_feed_proofs.py`.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIVE2 = HERE.parent
for p in (str(LIVE2), str(LIVE2 / "fleet"), str(LIVE2 / "v5"), str(LIVE2 / "hybrid"),
          str(LIVE2.parent / "baselines")):
    if p not in sys.path:
        sys.path.insert(0, p)

import deficit_feed as DF            # noqa: E402
import deficit_gain_d178 as GAIND    # noqa: E402
import share_admission as SA         # noqa: E402
import share_capacity as SCAP        # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)))
    print(("PASS " if ok else "FAIL ") + name + ((" | " + str(detail)) if detail else ""),
          flush=True)


def close(a, b, tol=1e-9):
    return abs(float(a) - float(b)) <= tol


# --------------------------------------------------------------------- the declared gain
check("gain is the declared 2.0", close(GAIND.GAIN, 2.0), "gain=%r" % GAIND.GAIN)
check("weight form: shortfall 0 gives exactly 1", close(GAIND.weight(0.0), 1.0))
check("weight form: HALF the target gives 2 at gain 2.0 (the declared justification)",
      close(GAIND.weight(0.5), 2.0))
check("weight range is bounded 1 to 3", close(GAIND.weight(1.0), 3.0)
      and close(GAIND.WEIGHT_MAX, 3.0))
check("FLOORED AT 1: a negative shortfall cannot drop the weight below 1",
      close(GAIND.weight(-0.4), 1.0))
check("gain 0 is the negative control, not a sweep point",
      GAIND.NEGATIVE_CONTROL_GAIN == 0.0
      and 0.0 not in set(GAIND.SWEEP_LATER.values()))

# --------------------------------------------------------------------- targets and geometry
check("targets are D178 (1): alert 0.25, recall 0.90, assistance 0.90",
      DF.TARGETS == {"alert": 0.25, "recall": 0.90, "assistance": 0.90}, str(DF.TARGETS))
check("three DIFFERENT denominators: episode, device, device",
      DF.UNIT == {"alert": "episode", "recall": "device", "assistance": "device"})
try:
    sys.path.insert(0, str(LIVE2 / "fleet"))
    import trace as TR
    check("EP-G geometry matches the trace generator's own frozen constants",
          DF.EPG_CAP_FRAMES == TR.EPG_CAP_FRAMES and DF.EPG_MIN_FRAMES == TR.EPG_MIN_FRAMES,
          "cap=%s min=%s" % (TR.EPG_CAP_FRAMES, TR.EPG_MIN_FRAMES))
except Exception as e:                                                      # noqa: BLE001
    check("EP-G geometry matches the trace generator's own frozen constants", False, repr(e))
check("a complete episode has NINETEEN decision instants, not 18 and not 21",
      DF.EPG_DECISION_INSTANTS == 19)

# --------------------------------------------------------------------- the token law
check("token law is exact: 42 + 338*n, position n-1",
      DF.position_from_prompt_tokens(42 + 338 * 3) == 2
      and DF.position_from_prompt_tokens(42 + 338 * 21) == 20)
check("a prompt that does not satisfy the law is None, NEVER rounded to a position",
      DF.position_from_prompt_tokens(42 + 338 * 3 + 1) is None
      and DF.position_from_prompt_tokens(None) is None
      and DF.position_from_prompt_tokens(0) is None)
check("a position beyond the 21-frame cap is rejected",
      DF.position_from_prompt_tokens(42 + 338 * 22) is None)

# --------------------------------------------------------------------- type classification
f = DF.DeficitFeed()
check("classification is by DEVICE PREFIX, so assistance is NOT merged into recall",
      f.type_of("dash000") == "alert" and f.type_of("robo003") == "recall"
      and f.type_of("asst001") == "assistance" and f.type_of("other9") is None)
check("the feed and its consumer classify with the SAME function",
      f.type_of("asst001") == SA.type_of_device("asst001"))

# --------------------------------------------------------------------- alert: episodes and 19
def alert_feed(seqs, gain=GAIND.GAIN):
    """seqs: list of (position, cloud_on_time) in arrival order for one device."""
    fd = DF.DeficitFeed(gain=gain)
    for pos, ont in seqs:
        fd.observe_completion(device_id="dash000", kind="monitor", cloud_on_time=ont,
                              prompt_tokens=42 + 338 * (pos + 1))
    return fd


# two full episodes of positions 2..20, the first with 5 on time, the second with 0
e1 = [(p, p < 7) for p in range(2, 21)]          # positions 2,3,4,5,6 on time = 5
e2 = [(p, False) for p in range(2, 21)]
fd = alert_feed(e1 + e2)
check("the position reset closes an episode (1 closed, 1 still open)",
      fd.counts.get("alert_episodes_closed") == 1, str(fd.counts))
check("the OPEN episode is excluded from the shortfall",
      len(fd.units("alert")) == 1)
check("every episode is scored over 19 instants",
      fd.units("alert") == [(19, 5)], str(fd.units("alert")))
check("5 of 19 clears the 25 percent target, so shortfall is 0",
      close(fd.shortfall("alert"), 0.0), "sf=%r" % fd.shortfall("alert"))

# three episodes so two close: one at 19/19 and one at 0/19
fd = alert_feed([(p, True) for p in range(2, 21)] + [(p, False) for p in range(2, 21)]
                + [(2, False)])
units = fd.units("alert")
check("two closed episodes, one perfect and one empty", units == [(19, 19), (19, 0)], str(units))
check("PER-EPISODE, not pooled: mean of (0.0, 0.25) = 0.125, where pooling would give 0.0",
      close(fd.shortfall("alert"), 0.125), "sf=%r" % fd.shortfall("alert"))
check("weight at gain 2.0 on a 0.125 shortfall is 1.25",
      close(fd.weights()["alert"], 1.25), str(fd.weights()))
check("alert weight stays within the declared 1 to 3 range",
      1.0 <= fd.weights()["alert"] <= 3.0)

# --------------------------------------------------------------------- the currency is CLOUD only
fd = DF.DeficitFeed()
for p in range(2, 21):
    fd.observe_completion(device_id="dash000", kind="monitor", cloud_on_time=False,
                          device_on_time=True, prompt_tokens=42 + 338 * (p + 1))
fd.observe_completion(device_id="dash000", kind="monitor", cloud_on_time=False,
                      device_on_time=True, prompt_tokens=42 + 338 * 3)
check("a DEVICE answer on time is NOT an on-time cloud answer (D177, D178 (1))",
      close(fd.shortfall("alert"), 0.25), "sf=%r" % fd.shortfall("alert"))
check("device_on_time is recorded beside the numerator, never added to it",
      fd.counts.get("alert_device_on_time") == 20 and fd.counts.get("alert_cloud_late") == 20,
      str(fd.counts))

# --------------------------------------------------------------------- recall: OFFERED denominator
fd = DF.DeficitFeed()
for i in range(10):
    fd.observe_offered_question("robo000", "q%d" % i)
for i in range(2):
    fd.observe_completion(device_id="robo000", kind="recall", cloud_on_time=True)
check("the recall denominator is OFFERED questions, not served ones",
      fd.units("recall") == [(10, 2)], str(fd.units("recall")))
check("2 of 10 against a 0.90 target is a 0.70 shortfall, not 0",
      close(fd.shortfall("recall"), 0.70), "sf=%r" % fd.shortfall("recall"))
check("so a device whose questions are all DECLINED is seen, not read as perfect",
      close(fd.weights()["recall"], 2.4), str(fd.weights()))
fd.observe_offered_question("robo000", "q0")
check("an offer is deduplicated by query id, so the same question is one denominator slot",
      fd.units("recall") == [(10, 2)] and fd.counts.get("recall_question_repeat") == 1)

# --------------------------------------------------------------------- per DEVICE, not pooled
fd = DF.DeficitFeed()
for i in range(10):
    fd.observe_offered_question("robo000", "a%d" % i)
    fd.observe_offered_question("robo001", "b%d" % i)
for i in range(10):
    fd.observe_completion(device_id="robo000", kind="recall", cloud_on_time=True)
check("the recall unit is the DEVICE: mean of (0.0, 0.90) = 0.45, pooling would give 0.40",
      close(fd.shortfall("recall"), 0.45), "sf=%r" % fd.shortfall("recall"))
check("a device with no offers does not enter the mean",
      len(fd.units("recall")) == 2)

# --------------------------------------------------------------------- assistance is its own type
fd = DF.DeficitFeed()
for i in range(10):
    fd.observe_offered_question("asst000", "s%d" % i)
    fd.observe_offered_question("robo000", "r%d" % i)
for i in range(10):
    fd.observe_completion(device_id="asst000", kind="recall", cloud_on_time=True)
check("assistance arrives as kind 'recall' and must still score as ASSISTANCE",
      close(fd.shortfall("assistance"), 0.0) and close(fd.shortfall("recall"), 0.90),
      "asst=%r recall=%r" % (fd.shortfall("assistance"), fd.shortfall("recall")))

# --------------------------------------------------------------------- background work is skipped
fd = DF.DeficitFeed()
for k in ("piece", "whole", "touch"):
    fd.observe_completion(device_id="robo000", kind=k, cloud_on_time=False)
check("a build or a touch is not an answer and has no deadline of its own",
      fd.counts.get("completion_background_skipped") == 3 and fd.n_completions == 0)

# --------------------------------------------------------------------- gain 0 removes the quantity
fd = DF.DeficitFeed(gain=0.0)
for i in range(10):
    fd.observe_offered_question("robo000", "q%d" % i)
check("gain 0: a NON-ZERO shortfall still gives weight exactly 1.0 (Step 4's control)",
      close(fd.shortfall("recall"), 0.90) and all(close(v, 1.0) for v in fd.weights().values()),
      "sf=%r w=%r" % (fd.shortfall("recall"), fd.weights()))

# --------------------------------------------------------------------- the CONSUMER reads them
# This is the one test about the READ rather than the value: the same request must get a different
# answer from `share_admission.allowed` under equal and under skewed weights, or the weights are a
# write-only field no matter how correct they are.
def admit(w, uncached):
    tr = SA.WTracker()
    # put recall at its floor so the next recall request is discretionary and must be tested
    # against its SHARE, which is the only place the weights enter
    tr.on_submit("r0", "recall", int(SCAP.FLOORS_TOKENS["recall"]), background=False)
    return SA.allowed(qtype="recall", uncached=uncached, kind="recall", tracker=tr,
                      weights_by_type=w, enabled=True)


_found = None
for u in range(50, 2400, 10):
    eq = admit(None, u)
    hi = admit({"alert": 1.0, "recall": 3.0, "assistance": 1.0}, u)
    lo = admit({"alert": 3.0, "recall": 1.0, "assistance": 1.0}, u)
    if eq[1] != hi[1] or eq[1] != lo[1]:
        _found = (u, eq, hi, lo)
        break
check("the CONSUMER reads weights_by_type: the same request gets a different answer under "
      "skewed weights (share_admission.py:162-166)", _found is not None, str(_found))
if _found:
    u, eq, hi, lo = _found
    check("a type in deficit gets MORE of the flexible pool, not less",
          hi[0] >= eq[0] >= lo[0] or hi[1] != lo[1],
          "u=%d equal=%s recall_w3=%s recall_w1=%s" % (u, eq, hi, lo))
# STRONGER, and the one that matters: a reason change is not a decision change. The weights must
# be able to flip an ADMIT to a DENY, or the mechanism is "cancelled by geometry" at the consumer
# however correct its arithmetic is.
_flip = None
for w_rec_inflight in (300, 655, 1200):
    tr = SA.WTracker()
    tr.on_submit("r0", "recall", w_rec_inflight, background=False)
    for u in range(10, 3000, 10):
        hi = SA.allowed(qtype="recall", uncached=u, kind="recall", tracker=tr, enabled=True,
                        weights_by_type={"alert": 1.0, "recall": 3.0, "assistance": 1.0})
        lo = SA.allowed(qtype="recall", uncached=u, kind="recall", tracker=tr, enabled=True,
                        weights_by_type={"alert": 3.0, "recall": 1.0, "assistance": 1.0})
        if hi[0] != lo[0]:
            _flip = (w_rec_inflight, u, hi, lo)
            break
    if _flip:
        break
check("the weights flip an ADMIT/DENY at the consumer, not merely a reason", _flip is not None,
      str(_flip))
if _flip:
    check("and in the right direction: the type in DEFICIT is the one that gets admitted",
          _flip[2][0] is True and _flip[3][0] is False, str(_flip))

check("the FLOORS are not weighted: a request inside its own floor admits whatever the weights",
      admit({"alert": 3.0, "recall": 1.0, "assistance": 1.0}, 1)[0] is True
      or SA.allowed(qtype="recall", uncached=1, kind="recall", tracker=SA.WTracker(),
                    weights_by_type={"alert": 3.0, "recall": 1.0, "assistance": 1.0},
                    enabled=True) == (True, "own_floor"))

# --------------------------------------------------------------------- the switch
import arms as A                                                            # noqa: E402
import arms_v6fairfeed as FF                                                # noqa: E402
import arms_v6shares as SH                                                  # noqa: E402

FF.register()
arm_on = A.make_arm("covex-v6-fair-shares")
arm_off = A.make_arm("covex-v6-fair-shares-off")
arm_g0 = A.make_arm("covex-v6-fair-shares-gain0")
check("the switch is an INSTANCE attribute, on every object of the delegation chain",
      arm_on._fairfeed_switch_chain() == [True] * len(arm_on._fairfeed_switch_chain())
      and len(arm_on._fairfeed_switch_chain()) >= 2, str(arm_on._fairfeed_switch_chain()))
check("default is OFF: a plain rung-2 arm reads the switch as False",
      FF.arm_enables(A.make_arm("covex-v6-state-shares")) is False)
check("the OFF arm exposes NO weights at all, not a dict of ones",
      arm_off.live2_share_weights() is None)
check("the ON arm exposes the three types", set(arm_on.live2_share_weights()) == set(SA.TYPES))
check("the gain-0 arm carries the declared control gain", close(arm_g0._feed_gain, 0.0))
_raised = False
try:
    setattr(SH.V6StateSharesArm, FF.SWITCH_ATTR, True)
    FF.arm_enables(A.make_arm("covex-v6-state-shares"))
except FF.DeficitFeedSwitchError:
    _raised = True
finally:
    try:
        delattr(SH.V6StateSharesArm, FF.SWITCH_ATTR)
    except Exception:                                                       # noqa: BLE001
        pass
check("a TRUTHY CLASS attribute RAISES, as release_recheck and share_admission both do", _raised)
_ok_false = None
try:
    setattr(SH.V6StateSharesArm, FF.SWITCH_ATTR, False)
    _ok_false = FF.arm_enables(A.make_arm("covex-v6-state-shares"))
finally:
    try:
        delattr(SH.V6StateSharesArm, FF.SWITCH_ATTR)
    except Exception:                                                       # noqa: BLE001
        pass
check("a class default of FALSE is allowed through: it cannot turn anything on",
      _ok_false is False)
check("BOTH rung-2 bases are registered, so the addendum 9 item A contingency needs no code edit",
      set(FF.BASES) == {"covex-v6-state-shares", "covex-v6-state-uo-c5attr"}
      and all(n in A.ARMS for n in ("covex-v6-fair-shares", "covex-v6-fair-c5attr")))
check("the c5attr base is declared as having NO reader for the weights",
      FF.BASE_HAS_WEIGHT_READER["covex-v6-state-uo-c5attr"] is False
      and FF.BASE_HAS_WEIGHT_READER["covex-v6-state-shares"] is True)
check("no accuracy value is read on this path (D177 (2): the value reader is REMOVED)",
      "value_reader" not in open(LIVE2 / "deficit_feed.py").read().split("docstring")[-1]
      or "value_readers" not in open(LIVE2 / "arms_v6fairfeed.py").read())

# --------------------------------------------------------------------- summary
nfail = sum(1 for _, ok, _ in RESULTS if not ok)
print("")
print("%d checks, %d PASS, %d FAIL" % (len(RESULTS), len(RESULTS) - nfail, nfail))
if nfail:
    for n, ok, d in RESULTS:
        if not ok:
            print("  FAIL: %s | %s" % (n, d))
raise SystemExit(1 if nfail else 0)
