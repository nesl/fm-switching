#!/usr/bin/env python3
"""Unit tests for the PER-DEVICE normalised deficit feed and its two consumers.

A PLAIN SCRIPT, because pytest is NOT installed in the fmtk env. Explicit pass/fail summary and a
non-zero exit on any failure, the same shape `d179_share_tests.py` uses.

These tests are about the ARITHMETIC and the PLUMBING, not about the policy: the normalised form,
the three denominators, the currency, the episode key, the switch's strictness, and that each
consumer can actually change an answer. The cell-level proofs are `d178_deficit_feed_proofs.py`.
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

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)))
    print(("PASS " if ok else "FAIL ") + name + ((" | " + str(detail)) if detail else ""),
          flush=True)


def close(a, b, tol=1e-9):
    return abs(float(a) - float(b)) <= tol


def target_is_required():
    try:
        GAIND.weight(0.1)                                      # type: ignore[call-arg]
    except TypeError:
        return True
    return False


# --------------------------------------------------------------------- the corrected declaration
check("gain is the declared 2.0, unchanged by the correction", close(GAIND.GAIN, 2.0))
check("the form is NORMALISED by the unit's own target",
      GAIND.NORMALISED_BY_TARGET is True and "shortfall_d / target_d" in GAIND.FORM, GAIND.FORM)
check("the superseded raw form is NAMED and marked NOT RUN", "NOT RUN" in GAIND.FORM_SUPERSEDED)
check("HALF its target gives exactly 2 for EVERY type, which the raw form did not",
      close(GAIND.weight(0.125, 0.25), 2.0) and close(GAIND.weight(0.45, 0.90), 2.0))
check("the range is 1 to 3 for EVERY type",
      close(GAIND.weight(0.25, 0.25), 3.0) and close(GAIND.weight(0.90, 0.90), 3.0)
      and close(GAIND.WEIGHT_MAX, 3.0))
check("FLOORED AT 1: a negative shortfall cannot drop the weight below 1",
      close(GAIND.weight(-0.4, 0.25), 1.0))
check("`target` is REQUIRED, so the superseded form cannot be reproduced by omitting it",
      target_is_required())
check("the raw form's unequal ranges are recorded for the correction's reader",
      GAIND.as_dict()["weight_range_under_the_superseded_form"]["alert"] == [1.0, 1.5])
check("gain 0 is the negative control, not a sweep point",
      GAIND.NEGATIVE_CONTROL_GAIN == 0.0 and 0.0 not in set(GAIND.SWEEP_LATER.values()))

# --------------------------------------------------------------------- targets and geometry
check("targets are D178 (1): alert 0.25, recall 0.90, assistance 0.90",
      DF.TARGETS == {"alert": 0.25, "recall": 0.90, "assistance": 0.90}, str(DF.TARGETS))
check("three DIFFERENT denominators, and alert's unit is the DEVICE-EPISODE",
      DF.UNIT == {"alert": "device-episode", "recall": "device", "assistance": "device"})
try:
    import trace as TR
    check("EP-G geometry matches the trace generator's own frozen constants",
          DF.EPG_CAP_FRAMES == TR.EPG_CAP_FRAMES and DF.EPG_MIN_FRAMES == TR.EPG_MIN_FRAMES,
          "cap=%s min=%s" % (TR.EPG_CAP_FRAMES, TR.EPG_MIN_FRAMES))
except Exception as e:                                                      # noqa: BLE001
    check("EP-G geometry matches the trace generator's own frozen constants", False, repr(e))
check("a complete episode has NINETEEN decision instants, not 18 and not 21",
      DF.EPG_DECISION_INSTANTS == 19)

# --------------------------------------------------------------------- the token-law cross-check
check("token law is exact where it applies: 42 + 338*n, position n-1",
      DF.position_from_prompt_tokens(42 + 338 * 3) == 2
      and DF.position_from_prompt_tokens(42 + 338 * 21) == 20)
check("a prompt that does not satisfy the law is None, NEVER rounded to a position",
      DF.position_from_prompt_tokens(42 + 338 * 3 + 1) is None
      and DF.position_from_prompt_tokens(None) is None
      and DF.position_from_prompt_tokens(0) is None)

# --------------------------------------------------------------------- type classification
f = DF.DeficitFeed()
check("classification is by DEVICE PREFIX, so assistance is NOT merged into recall",
      f.type_of("dash000") == "alert" and f.type_of("robo003") == "recall"
      and f.type_of("asst001") == "assistance" and f.type_of("other9") is None)
check("the feed and its consumers classify with the SAME function",
      f.type_of("asst001") == SA.type_of_device("asst001"))


# --------------------------------------------------------------------- alert: PER DEVICE episodes
def alert_feed(per_device, gain=GAIND.GAIN):
    fd = DF.DeficitFeed(gain=gain)
    for did, seq in per_device.items():
        for epid, ont in seq:
            fd.observe_completion(device_id=did, kind="monitor", cloud_on_time=ont,
                                  episode_id=epid, episode_index=None, prompt_tokens=None)
    return fd


fd = alert_feed({"dash000": [("e0", p < 7) for p in range(2, 21)]
                 + [("e1", False) for _ in range(19)] + [("e2", False)]})
check("episode_id from the HOOK closes an episode (2 closed, 1 open)",
      fd.counts.get("alert_episodes_closed") == 2, str(fd.counts))
check("the hook is the AUTHORITY, not the token law",
      fd.counts.get("alert_episode_key_from_record", 0) > 0
      and fd.counts.get("alert_episode_key_from_token_law", 0) == 0)
check("PER-EPISODE, not pooled: mean of (0.0, 0.25) = 0.125 for this device",
      close(fd.shortfall_device("dash000"), 0.125), "sf=%r" % fd.shortfall_device("dash000"))
check("NORMALISED: 0.125 / 0.25 = 0.5, so w_d = 2.0 exactly",
      close(fd.weight_device("dash000"), 2.0), "w=%r" % fd.weight_device("dash000"))
check("the RAW form would have given 1.25 here, which is the correction's whole point",
      close(1.0 + GAIND.GAIN * 0.125, 1.25))
check("a device with no closed episode has shortfall 0 and weight 1",
      close(fd.shortfall_device("dash005"), 0.0) and close(fd.weight_device("dash005"), 1.0))

fd = alert_feed({"dash000": [("e0", False) for _ in range(19)] + [("e1", False)],
                 "dash001": [("f0", True) for _ in range(19)] + [("f1", True)]})
check("PER DEVICE: the starved device is 3.0 and its satisfied peer is 1.0",
      close(fd.weight_device("dash000"), 3.0) and close(fd.weight_device("dash001"), 1.0),
      "%r %r" % (fd.weight_device("dash000"), fd.weight_device("dash001")))
check("the per-TYPE mean is kept only as a DIAGNOSTIC and is NOT what either consumer reads",
      close(fd.type_shortfall("alert"), 0.125), "diag=%r" % fd.type_shortfall("alert"))
check("the SPLIT takes the MAXIMUM over pending devices, not the mean",
      close(fd.weights_by_type(["dash000", "dash001"])["alert"], 3.0),
      str(fd.weights_by_type(["dash000", "dash001"])))
check("a type with NO pending device gets 1.0, so it holds no share it cannot use",
      close(fd.weights_by_type(["dash001"])["recall"], 1.0)
      and close(fd.weights_by_type([])["alert"], 1.0))
check("pending is what narrows it: only the satisfied device pending gives 1.0, not 3.0",
      close(fd.weights_by_type(["dash001"])["alert"], 1.0))

fd = DF.DeficitFeed()
for p in range(2, 8):
    fd.observe_completion(device_id="dash000", kind="monitor", cloud_on_time=True,
                          episode_id="e0", episode_index=p, prompt_tokens=42 + 338 * (p + 1))
check("the token law is CROSS-CHECKED against episode_index and agrees",
      fd.counts.get("alert_episode_key_agree") == 6
      and not fd.counts.get("alert_episode_key_disagree"), str(fd.counts))
fd.observe_completion(device_id="dash000", kind="monitor", cloud_on_time=True,
                      episode_id="e0", episode_index=9, prompt_tokens=42 + 338 * 3)
check("a DISAGREEMENT is counted, not smoothed",
      fd.counts.get("alert_episode_key_disagree") == 1)

# --------------------------------------------------------------------- the currency is CLOUD only
fd = DF.DeficitFeed()
for i in range(19):
    fd.observe_completion(device_id="dash000", kind="monitor", cloud_on_time=False,
                          device_on_time=True, episode_id="e0")
fd.observe_completion(device_id="dash000", kind="monitor", cloud_on_time=False,
                      device_on_time=True, episode_id="e1")
check("a DEVICE answer on time is NOT an on-time cloud answer (D177, D178 (1))",
      close(fd.shortfall_device("dash000"), 0.25) and close(fd.weight_device("dash000"), 3.0),
      "sf=%r" % fd.shortfall_device("dash000"))
check("device_on_time is recorded beside the numerator, never added to it",
      fd.counts.get("alert_device_on_time") == 20 and fd.counts.get("alert_cloud_late") == 20)

# --------------------------------------------------------------------- recall: OFFERED denominator
fd = DF.DeficitFeed()
for i in range(10):
    fd.observe_offered_question("robo000", "q%d" % i)
for i in range(2):
    fd.observe_completion(device_id="robo000", kind="recall", cloud_on_time=True)
check("the recall denominator is OFFERED questions, not served ones",
      fd.units("recall") == [(10, 2)], str(fd.units("recall")))
check("2 of 10 against a 0.90 target is a 0.70 shortfall, not 0",
      close(fd.shortfall_device("robo000"), 0.70))
check("NORMALISED: 0.70 / 0.90 gives w_d = 2.5556",
      close(fd.weight_device("robo000"), 1.0 + 2.0 * (0.70 / 0.90)),
      "w=%r" % fd.weight_device("robo000"))
fd.observe_offered_question("robo000", "q0")
check("an offer is deduplicated by query id, so the same question is one denominator slot",
      fd.units("recall") == [(10, 2)] and fd.counts.get("recall_question_repeat") == 1)

# --------------------------------------------------------------------- assistance is its own type
fd = DF.DeficitFeed()
for i in range(10):
    fd.observe_offered_question("asst000", "s%d" % i)
    fd.observe_offered_question("robo000", "r%d" % i)
for i in range(10):
    fd.observe_completion(device_id="asst000", kind="recall", cloud_on_time=True)
check("assistance arrives as kind 'recall' and must still score as ASSISTANCE",
      close(fd.weight_device("asst000"), 1.0) and close(fd.weight_device("robo000"), 3.0),
      "asst=%r robo=%r" % (fd.weight_device("asst000"), fd.weight_device("robo000")))

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
      close(fd.shortfall_device("robo000"), 0.90) and close(fd.weight_device("robo000"), 1.0)
      and all(close(v, 1.0) for v in fd.weights_by_type(["robo000"]).values()))


# --------------------------------------------------------------------- consumer 2 reads the split
def admit(w, uncached, inflight=0):
    tr = SA.WTracker()
    if inflight:
        tr.on_submit("r0", "recall", int(inflight), background=False)
    return SA.allowed(qtype="recall", uncached=uncached, kind="recall", tracker=tr,
                      weights_by_type=w, enabled=True)


_flip = None
for infl in (300, 655, 1200):
    for u in range(10, 3000, 10):
        hi = admit({"alert": 1.0, "recall": 3.0, "assistance": 1.0}, u, infl)
        lo = admit({"alert": 3.0, "recall": 1.0, "assistance": 1.0}, u, infl)
        if hi[0] != lo[0]:
            _flip = (infl, u, hi, lo)
            break
    if _flip:
        break
check("CONSUMER 2 (split) can flip an ADMIT/DENY, not merely a reason", _flip is not None,
      str(_flip))
if _flip:
    check("and in the right direction: the type in DEFICIT is the one admitted",
          _flip[2][0] is True and _flip[3][0] is False)
check("the FLOORS are not weighted: a request inside its own floor admits whatever the weights",
      SA.allowed(qtype="recall", uncached=1, kind="recall", tracker=SA.WTracker(),
                 weights_by_type={"alert": 3.0, "recall": 1.0, "assistance": 1.0},
                 enabled=True) == (True, "own_floor"))

# --------------------------------------------------------------------- the arm and both consumers
import arms as A                                                            # noqa: E402
import arms_v6fairfeed as FF                                                # noqa: E402
import arms_v6shares as SH                                                  # noqa: E402
import hybrid_arm as HA                                                     # noqa: E402

FF.register()
arm_on = A.make_arm("covex-v6-fair-shares")
arm_off = A.make_arm("covex-v6-fair-shares-off")
arm_g0 = A.make_arm("covex-v6-fair-shares-gain0")
arm_oo = A.make_arm("covex-v6-fair-shares-orderonly")
arm_so = A.make_arm("covex-v6-fair-shares-splitonly")

check("the switch is an INSTANCE attribute on every object of the delegation chain",
      arm_on._fairfeed_switch_chain() == [True] * len(arm_on._fairfeed_switch_chain())
      and len(arm_on._fairfeed_switch_chain()) >= 2, str(arm_on._fairfeed_switch_chain()))
check("default is OFF: a plain rung-2 arm reads the switch as False",
      FF.arm_enables(A.make_arm("covex-v6-state-shares")) is False)
check("the OFF arm exposes NO weights at all, not a dict of ones",
      arm_off.live2_share_weights() is None)
# Compared by class NAME, not by identity: `hybrid_arm` is importable both as `hybrid_arm` and as
# `hybrid.hybrid_arm`, which are two module objects with two distinct `HybridArm` classes, so an
# isinstance check here fails for a reason that has nothing to do with the override.
check("the ORDERING override is installed on the INNER HybridArm, as an INSTANCE attribute",
      type(arm_on._fairfeed_order_core).__name__ == "HybridArm"
      and "_deficit_order_key" in vars(arm_on._fairfeed_order_core),
      type(arm_on._fairfeed_order_core).__name__)
check("the frozen CLASS default is untouched, so no other arm can inherit the override",
      close(HA.HybridArm._deficit_order_key(arm_off, "robo000", "recall"), 0.0))
check("a plain rung-2 arm's core has NOTHING shadowed",
      "_deficit_order_key" not in vars(A.make_arm("covex-v6-state-shares").hybrid_core()))

arm_on._fairfeed_session_device = {"robo000|s0": "robo000"}
for i in range(10):
    arm_on._feed.observe_offered_question("robo000", "q%d" % i)
k_dev = arm_on._fairfeed_order_core._deficit_order_key("robo000", "recall")
k_sess = arm_on._fairfeed_order_core._deficit_order_key("robo000|s0", "recall")
k_none = arm_on._fairfeed_order_core._deficit_order_key(None, "dash")
check("CONSUMER 1 (ordering) returns the NEGATIVE w_d, so a larger w_d sorts FIRST",
      close(k_dev, -3.0), "key=%r" % k_dev)
check("it resolves a SESSION id through the roster as well as a device id",
      close(k_sess, -3.0), "key=%r" % k_sess)
check("an UNRESOLVED item takes the neutral 0.0 and is COUNTED, never guessed",
      close(k_none, 0.0) and arm_on._feed.counts.get("order_key_unresolved_device") == 1)
check("ordering is NEUTRAL on the split-only arm (nothing shadowed)",
      "_deficit_order_key" not in vars(arm_so._fairfeed_order_core)
      and arm_so.live2_share_weights() is not None)
check("the split is OFF on the order-only arm (no weights exposed at all)",
      arm_oo.live2_share_weights() is None
      and "_deficit_order_key" in vars(arm_oo._fairfeed_order_core))
check("gain 0 leaves BOTH consumers live and instrumented, which makes it the comparator",
      arm_g0._feed_ordering and arm_g0._feed_split
      and "_deficit_order_key" in vars(arm_g0._fairfeed_order_core)
      and arm_g0.live2_share_weights() is not None)
for i in range(10):
    arm_g0._feed.observe_offered_question("robo000", "q%d" % i)
check("and at gain 0 the ordering key is the SAME CONSTANT for every device, so it cannot reorder",
      close(arm_g0._fairfeed_order_core._deficit_order_key("robo000", "recall"), -1.0)
      and close(arm_g0._fairfeed_order_core._deficit_order_key("robo001", "recall"), -1.0))

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
check("BOTH rung-2 bases are registered, and the four one-factor names exist",
      set(FF.BASES) == {"covex-v6-state-shares", "covex-v6-state-uo-c5attr"}
      and all(n in A.ARMS for n in ("covex-v6-fair-shares", "covex-v6-fair-c5attr",
                                    "covex-v6-fair-shares-orderonly",
                                    "covex-v6-fair-shares-splitonly")))
check("no accuracy value is read on this path (D177 (2): the value reader is REMOVED)",
      "value_readers" not in open(LIVE2 / "arms_v6fairfeed.py").read()
      and "value_readers" not in open(LIVE2 / "deficit_feed.py").read())

# --------------------------------------------------------------------- summary
nfail = sum(1 for _, ok, _ in RESULTS if not ok)
print("")
print("%d checks, %d PASS, %d FAIL" % (len(RESULTS), len(RESULTS) - nfail, nfail))
if nfail:
    for n, ok, d in RESULTS:
        if not ok:
            print("  FAIL: %s | %s" % (n, d))
raise SystemExit(1 if nfail else 0)
