#!/usr/bin/env python3
"""D178 (1) PER-TYPE DEFICIT FEED: the three shortfalls, their three denominators, and the weights.

    w_t = 1 + GAIN * shortfall_t,  floored at 1,  per QUERY TYPE t  (gain declared in
    `deficit_gain_d178.py`, pre-registered at 2.0 before any cell of this rung ran)

This is the mechanism of covex-v6-fair as D177 (2) leaves it: THE DEFICIT FEED ONLY. The value
reader is removed and is not imported here; the quality table is reporting-only and no accuracy
number enters any quantity below.

THE CURRENCY IS ON-TIME CLOUD ANSWERS, AND THAT IS A CHANGE FROM `arms_v6fair.py` (D177). The
coordinator reports `cloud_on_time` and `device_on_time` SEPARATELY and its comment says combining
them is a policy choice belonging in the arm (coordinator.py:1624-1631). `arms_v6fair.V6FairArm`
took the OR, which was right under D155 (3)'s "by the deadline from either source". It is wrong
under D177 and D178 (1), which write all three targets in terms of an ON-TIME CLOUD ANSWER:

    alert       at least 25 % of the episode's decision instants RECEIVE AN ON-TIME CLOUD ANSWER
    recall      90 % of the device's questions RECEIVE AN ON-TIME CLOUD ANSWER
    assistance  90 % of the device's questions within 2 s

So the combination chosen HERE is `cloud_on_time` ALONE. `device_on_time` is recorded beside it,
never added to it: the device always has an answer (D19, D87), so an OR-combined target is met by
construction on every opportunity the device answers in time and the shortfall would be
structurally near zero. Measured on the committed covex-v6-state seed-5 cell: the alert type's
on-time CLOUD fraction is 0.2089, below its 0.25 target, while every one of its 11,769 instants
has a device answer. An OR feed therefore cannot see the one deficit this rung exists to act on.
`assistance` is read the same way, because D177 makes on-time cloud answers the currency
throughout; its deadline IS 2.0 s, so "within 2 s" and "on time" are the same test for it.

THREE TARGETS, THREE DIFFERENT DENOMINATORS (D178 (1)), each CHECKED against committed cells
rather than assumed. The check is in `d178_deficit_feed_proofs.py`; the numbers below are from
`results/orchestration/live2/frozen_test/runs/covex-v6-state_n16_s5_1200s_h27_3t_L3_epg_rq30`.

  alert       unit = EPISODE. Denominator = NINETEEN decision instants, a DECLARED CONSTANT, not a
              count. An episode is the append-only EP-G context of D148 with a 21-frame cap, and
              D153's floor makes instants before the episode's THIRD frame not decision instants
              for any arm, so an episode's decision instants are positions 2 to 20 inclusive:
              NINETEEN, not 18 and not 21. VERIFIED on the committed cell: 714 episodes, instants
              per episode min 2, median 19, max 19, and the short ones are a play ending
              mid-episode.
              THE BIAS OF THE CONSTANT IS MEASURED, NOT ASSUMED. About 27 percent of episodes are
              truncated by a play ending, and giving those 19 instants overstates their shortfall.
              On the committed cell: true per-episode denominators give a type shortfall of 0.1427,
              the flat 19 over the SAME episodes gives 0.1467, and the flat 19 over the episodes
              THIS FEED detects gives 0.1456. So the constant costs +0.0029 on the shortfall and
              +0.006 on the weight at gain 2.0. An earlier version counted each episode's offered
              instants and reconstructed never-served episodes from the cap; the replay positive
              control in `d178_deficit_feed_proofs.py` rejected it, 1,169 episodes against the true
              714, because a completion arrives one to three instants AFTER its own instant was
              offered and the attribution charged those later instants to the episode being closed.
              A constant with a measured 2 percent bias is worth more than a reconstruction with an
              unmeasured one.
              WHY PER EPISODE AND NOT POOLED, measured rather than argued: the mean per-episode
              shortfall on that cell is 0.1427 and the POOLED shortfall over all 11,769 instants
              is 0.0411. Pooling understates the alert deficit by 3.5x, because 486 of 714
              episodes are below target while the type as a whole is only just below it. That is
              consistency check 3's "a real effect averaged into undetectability", and it is the
              reason the episode is the unit here at all.
  recall      unit = DEVICE. Denominator = the device's OFFERED recall questions. OFFERED, not
              served: the committed base offers 485 recall questions across four cells and sends
              179, and a feed counting only completions sees a 100 percent rate for a device whose
              questions are all being declined. That is the exact case the weighting exists to
              catch and is the blind spot `arms_v6fair` records as `deficit_feed_unseen_declines`.
              Here the denominator is taken from the OFFER instead, so the blind spot is closed
              rather than counted.
  assistance  unit = DEVICE. Denominator = the device's OFFERED assistance questions, same reason.

A DEFINITION POINT ON THE RECALL DENOMINATOR, because it is load-bearing and is not obvious. It
counts OPPORTUNITIES, so a D159 (C) re-ask of a question counts again. It has to: a re-ask has its
own arrival, its own 3 s deadline and its own admission decision, and it is the only thing
observable online. But it means the denominator is NOT the count of distinct questions, and the
difference is large on a single device. The traced unit in `d178_deficit_feed_trace.py` is robo001
on the committed seed-5 cell: SIX offered opportunities, of which FOUR are one question re-asked,
two were sent and one arrived on time, so the shortfall is 0.733 and the weight 2.467. The offline
headline scores the same traffic as repeated measures WITHIN question, clustered by question
(D161), which is a different denominator on purpose. The online counter and the offline score are
therefore not the same quantity and must not be quoted against each other.

CLASSIFICATION IS BY DEVICE-ID PREFIX, NOT BY `kind`. The completion hook's `kind` is "monitor"
for alert and "recall" FOR BOTH recall AND assistance: on the committed cell every `asst00x`
completion arrives as kind "recall" with `deadline_s` 2.0, and every `robo00x` as kind "recall"
with 3.0. `arms_v6fair.py:129` maps kind monitor -> dashcam and EVERYTHING ELSE -> robot, which
merges assistance into recall. Prefix classification is `share_admission.type_of_device`, the same
function the consumer of these weights uses, so the weights and the shares cannot disagree about
which type a device is.

HOW THE EPISODE IS IDENTIFIED, since the completion hook does not carry `episode_id`. Preferred
source first, and which one fired is COUNTED, never assumed:

  1. `rec["episode_id"]`, if the coordinator ever carries it. It does NOT today; the one-line
     additive change is named in this build's report. This branch is dead code until then and the
     counter `alert_episode_key_from_record` will read 0, which is how a reader can tell.
  2. DERIVED from the EP-G prompt-token law. Under EP-G a monitor request's prompt is the whole
     episode, `prompt_tokens = 42 + 338 * n_frames` (`bodies.epg_prompt_tokens`, and the
     coordinator's own comment at coordinator.py:846 says est_tokens "is what the engine will
     report as prompt_tokens"). So the episode POSITION is exact: pos = (pt - 42) / 338 - 1.
     Positions rise within an episode and reset at its start, so a position that does not rise is
     a new episode. NOT A PROXY, and the positive control says so: on the committed LIVE seed-5
     cell all 8,312 dashcam requests satisfy (pt - 42) % 338 == 0 with positions in 2 to 20,
     ZERO violations. Non-conforming prompt_tokens are counted (`alert_pos_unparsable`) and never
     guessed at.

WHAT THE DERIVATION CANNOT SEE, stated rather than discovered later. Boundaries are visible only at
a SERVED instant, so an episode the policy never serves at all is INVISIBLE to the feed and its
shortfall of the full 0.25 is never counted. Measured on the committed cell: 4 of 714 episodes have
no served request, and the feed detects 707 of 714 (99.0 percent). Excluding the unserved ones
entirely moves the type shortfall from 0.1427 to 0.1421, so the blind spot is 0.0006 and runs in
the direction of UNDERSTATING the alert deficit. It is reported, not smoothed, and it is the one
thing the one-line `episode_id` addition to the completion hook would fix outright.

THE OPEN EPISODE IS EXCLUDED from the shortfall. A partial episode reads as a shortfall whatever
the policy does, because its instants have not all happened yet; counting it would make the weight
a function of where in its episode each device happens to be. Only CLOSED episodes enter, and
`alert_episodes_open` reports how many are excluded at any moment.

A STRUCTURAL CONSEQUENCE OF THE DECLARED FORM, RECORDED BECAUSE IT IS NOT OBVIOUS AND IT IS THE
USER'S TO RULE ON. `w_t = 1 + gain * shortfall_t` is UNNORMALISED, and a shortfall cannot exceed
its own target, so the reachable weight range is `1` to `1 + gain * target_t`, which is NOT the same
range for the three types:

    alert       target 0.25  ->  w in [1.0, 1.5]
    recall      target 0.90  ->  w in [1.0, 2.8]
    assistance  target 0.90  ->  w in [1.0, 2.8]

So the declaration's "bounded at 1 to 3" is reachable only by a type whose target is 1, and the
type with the LARGEST measured per-unit deficit (alert, 0.146 on the committed seed-5 cell) has the
SMALLEST reachable range. Measured on that cell the three weights are 1.292, 1.210 and 1.000, and
alert sits 58 percent of the way to its own ceiling while recall sits 12 percent of the way to its,
so the unnormalised form moves alert's cut of the flexible pool by about 3 percent of its share
when alert is the one type below target. Spec v6 section 1 states the objective's changes are
"normalised by the device's own target window so sparse and dense devices are comparable
(D122 B2)", and `shortfall_t / target_t` would be that normalisation, giving w 2.17 against 1.23 on
the same cell. THE DECLARED FORM IS USED HERE AS DECLARED; the alternative is named for the D178 (2)
sweep and is not substituted.

THE WINDOW IS CUMULATIVE OVER THE RUN, deliberately and as the only option that adds no knob. A
sliding window would be a tuned parameter, and D151 (1)'s margin exists to stop the objective
acquiring tuned parameters. The consequence is that weights move fastest early and settle, which
proof (c) of this build reports as a per-type min / median / max over time rather than one number.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import deficit_gain_d178 as GAIND
import share_admission as SA

# ---- D178 (1) targets. Per type, from the use case, NOT from any achieved result.
TARGETS: Dict[str, float] = {"alert": 0.25, "recall": 0.90, "assistance": 0.90}
TARGET_SOURCE = "D178 (1), spec v6 sections 2 and 8"
# The unit each target's denominator is counted over. Three targets, three denominators.
UNIT: Dict[str, str] = {"alert": "episode", "recall": "device", "assistance": "device"}

# ---- the EP-G episode geometry, from the trace generator's own frozen constants
EPG_CAP_FRAMES = 21                 # fleet/trace.py EPG_CAP_FRAMES (D148)
EPG_MIN_FRAMES = 3                  # fleet/trace.py EPG_MIN_FRAMES (D153)
EPG_FIRST_POS = EPG_MIN_FRAMES - 1  # 2: the first position that is a decision instant
EPG_LAST_POS = EPG_CAP_FRAMES - 1   # 20
# NINETEEN decision instants in a complete episode. Verified against the committed cell.
EPG_DECISION_INSTANTS = EPG_LAST_POS - EPG_FIRST_POS + 1
assert EPG_DECISION_INSTANTS == 19

# ---- the EP-G prompt-token law, bodies.epg_prompt_tokens
EPG_TEXT_TOKENS = 42
EPG_TOK_PER_FRAME = 338


def position_from_prompt_tokens(prompt_tokens: Any) -> Optional[int]:
    """The episode position of a monitor request, or None if the prompt does not follow the law.

    Exact, not a proxy: the law is `42 + 338 * n_frames` and the position is `n_frames - 1`. A
    prompt that does not satisfy it is NOT rounded to the nearest position, because a rounded
    position would silently invent an episode boundary.
    """
    if prompt_tokens is None:
        return None
    try:
        pt = int(prompt_tokens)
    except (TypeError, ValueError):
        return None
    rem = pt - EPG_TEXT_TOKENS
    if rem <= 0 or rem % EPG_TOK_PER_FRAME:
        return None
    pos = rem // EPG_TOK_PER_FRAME - 1
    return pos if 0 <= pos <= EPG_LAST_POS else None


class _Unit:
    """One scored unit: an episode, or a device's question stream. offered is the DENOMINATOR."""

    __slots__ = ("offered", "on_time")

    def __init__(self) -> None:
        self.offered = 0
        self.on_time = 0

    def shortfall(self, target: float) -> float:
        if self.offered <= 0:
            return 0.0
        return max(float(target) - self.on_time / self.offered, 0.0)


class _AlertDevice:
    """The open episode of one alert device, plus the on-time count of each episode it closed."""

    __slots__ = ("open_on_time", "last_pos", "seen", "closed", "epid")

    def __init__(self) -> None:
        self.open_on_time = 0
        self.last_pos: Optional[int] = None
        self.seen: set = set()
        self.closed: List[int] = []
        self.epid: Optional[str] = None


class DeficitFeed:
    """Per-type shortfalls and the per-type weights, fed from offers and from completions.

    Three feeds in, one dict out:

        observe_offered_instant(device_id, opportunity_id)   alert denominator
        observe_offered_question(device_id, query_id)        recall / assistance denominator
        observe_completion(...)                              every numerator

    `weights()` is the only output, and it is what `share_admission.allowed(weights_by_type=...)`
    consumes. Nothing here reads a quality table or an accuracy value (D177 (2)).
    """

    def __init__(self, gain: float = GAIND.GAIN) -> None:
        self.gain = float(gain)
        self.counts: Dict[str, int] = {}
        self._alert: Dict[str, _AlertDevice] = {}
        self._dev: Dict[str, _Unit] = {}            # recall and assistance, per device
        self._dev_seen: Dict[str, set] = {}
        self.n_offers = 0
        self.n_completions = 0

    # ---- bookkeeping -------------------------------------------------------------------------
    def _bump(self, k: str, n: int = 1) -> None:
        self.counts[k] = self.counts.get(k, 0) + n

    @staticmethod
    def type_of(device_id: Any) -> Optional[str]:
        return SA.type_of_device(str(device_id or ""))

    # ---- the denominators --------------------------------------------------------------------
    def observe_offered_instant(self, device_id: Any, opportunity_id: Any) -> None:
        """One OFFERED alert decision instant. REPORTING ONLY: it is NOT in any denominator.

        Deduplicated by opportunity id, because the same instant is surfaced in the roster on
        every 100 ms period until it resolves and a count of item-periods is not a count of
        instants (the confusion `share_capacity.py` records about `c5_dash_held`). It is kept
        because it is the one independent check on the episode count: on the dry seed-4 posted cell
        it reads 11,764, which is exactly the monitor opportunity count D174 (2) measured on the
        committed cells, so the offer stream the feed sees is the whole stream and not a sample.
        """
        if self.type_of(device_id) != "alert" or opportunity_id is None:
            return
        st = self._alert.setdefault(str(device_id), _AlertDevice())
        oid = str(opportunity_id)
        if oid in st.seen:
            self._bump("alert_instant_repeat")
            return
        st.seen.add(oid)
        self.n_offers += 1
        self._bump("alert_instants_offered")

    def observe_offered_question(self, device_id: Any, query_id: Any) -> None:
        """One OFFERED recall or assistance question, deduplicated by query id."""
        t = self.type_of(device_id)
        if t not in ("recall", "assistance") or query_id is None:
            return
        did = str(device_id)
        seen = self._dev_seen.setdefault(did, set())
        qid = str(query_id)
        if qid in seen:
            self._bump(t + "_question_repeat")
            return
        seen.add(qid)
        self._dev.setdefault(did, _Unit()).offered += 1
        self.n_offers += 1
        self._bump(t + "_questions_offered")

    # ---- the numerator -----------------------------------------------------------------------
    def observe_completion(self, *, device_id: Any, kind: Any, cloud_on_time: Any,
                           device_on_time: Any = None, prompt_tokens: Any = None,
                           episode_id: Any = None) -> None:
        """One completion. The numerator is `cloud_on_time` ALONE (D177, D178 (1))."""
        t = self.type_of(device_id)
        if t is None:
            self._bump("completion_untyped")
            return
        if str(kind) in ("piece", "whole", "touch"):
            self._bump("completion_background_skipped")
            return
        self.n_completions += 1
        ont = bool(cloud_on_time)
        self._bump(t + ("_cloud_on_time" if ont else "_cloud_late"))
        # recorded beside, NEVER added to the numerator: see the module docstring
        if device_on_time is not None:
            self._bump(t + ("_device_on_time" if bool(device_on_time) else "_device_late"))
        if t == "alert":
            self._alert_completion(str(device_id), ont, prompt_tokens, episode_id)
        else:
            self._dev.setdefault(str(device_id), _Unit()).on_time += 1 if ont else 0

    def _alert_completion(self, device_id: str, on_time: bool, prompt_tokens: Any,
                          episode_id: Any) -> None:
        st = self._alert.setdefault(device_id, _AlertDevice())
        if episode_id is not None:
            # branch 1: the coordinator carried the key. Dead until the hook adds the field.
            self._bump("alert_episode_key_from_record")
            boundary = st.epid is not None and st.epid != str(episode_id)
            st.epid = str(episode_id)
        else:
            pos = position_from_prompt_tokens(prompt_tokens)
            if pos is None:
                self._bump("alert_pos_unparsable")
                boundary = False
            else:
                self._bump("alert_episode_key_from_token_law")
                # positions rise within an episode and restart at its first decision instant, so
                # a position that does not rise is the first served instant of the next episode
                boundary = st.last_pos is not None and pos <= st.last_pos
                st.last_pos = pos
        if boundary:
            st.closed.append(st.open_on_time)
            st.open_on_time = 0
            self._bump("alert_episodes_closed")
        st.open_on_time += 1 if on_time else 0

    # ---- the output --------------------------------------------------------------------------
    def shortfall(self, qtype: str) -> float:
        """The type's shortfall: the MEAN over its units of each unit's own clipped shortfall.

        The mean over units, not a pooled ratio, because the targets are per unit (D178 (1)) and
        because a pooled ratio hides a distribution: on the committed seed-5 cell the two differ
        by 3.5x on alert.
        """
        t = TARGETS.get(qtype)
        if t is None:
            return 0.0
        if qtype == "alert":
            vals = [max(t - (ot / EPG_DECISION_INSTANTS), 0.0)
                    for st in self._alert.values() for ot in st.closed]
        else:
            vals = [u.shortfall(t) for did, u in self._dev.items()
                    if self.type_of(did) == qtype and u.offered > 0]
        if not vals:
            return 0.0
        return sum(vals) / len(vals)

    def weights(self) -> Dict[str, float]:
        """`w_t = 1 + gain * shortfall_t`, floored at 1. What `allowed(weights_by_type=)` reads."""
        return {t: GAIND.weight(self.shortfall(t), self.gain) for t in SA.TYPES}

    def units(self, qtype: str) -> List[Tuple[int, int]]:
        """(offered, on_time) per scored unit of the type, for a distribution report."""
        if qtype == "alert":
            return [(EPG_DECISION_INSTANTS, ot)
                    for st in self._alert.values() for ot in st.closed]
        return [(u.offered, u.on_time) for did, u in sorted(self._dev.items())
                if self.type_of(did) == qtype and u.offered > 0]

    def as_dict(self) -> Dict[str, Any]:
        open_eps = sum(1 for st in self._alert.values() if st.last_pos is not None)
        self.counts["alert_episodes_open"] = open_eps
        out: Dict[str, Any] = {
            "gain": self.gain, "gain_ruling": GAIND.GAIN_RULING,
            "targets": dict(TARGETS), "target_source": TARGET_SOURCE, "units": dict(UNIT),
            "currency": "on-time CLOUD answers only (D177, D178 (1)); device_on_time recorded, "
                        "never added to the numerator",
            "alert_decision_instants_per_episode": EPG_DECISION_INSTANTS,
            "n_offers": self.n_offers, "n_completions": self.n_completions,
            "weights": {k: round(v, 6) for k, v in self.weights().items()},
            "shortfall": {t: round(self.shortfall(t), 6) for t in SA.TYPES},
            "n_units": {t: len(self.units(t)) for t in SA.TYPES},
            "counts": dict(sorted(self.counts.items())),
        }
        return out
