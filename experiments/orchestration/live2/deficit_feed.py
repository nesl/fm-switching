#!/usr/bin/env python3
"""PER-DEVICE DEFICIT FEED: three denominators, the normalised weight, and its two consumers.

    w_d = 1 + GAIN * (shortfall_d / target_d),  floored at 1,  PER DEVICE d

GAIN is declared and pre-registered in `deficit_gain_d178.py` at 2.0, and the NORMALISATION by the
unit's own target is the addendum 12 item 2 correction, recorded in place in that module's
docstring with the original wording, the error and its direction. The raw unnormalised form is not
run at any gain. The weight range is 1 to 3 for EVERY type, because `shortfall_d / target_d` is in
[0, 1] by construction.

PER DEVICE, NOT PER TYPE (addendum 12 item 1, D3, D122 B). The unit of each target is the device,
and for alert it is the device's EPISODE. The per-TYPE figures an earlier build of this module
reported are kept only as DIAGNOSTICS (`type_shortfall`), because the flexible-split consumer needs
one number per type and takes the MAXIMUM over that type's pending devices, not an average.

THE CURRENCY IS ON-TIME CLOUD ANSWERS ALONE (D177). The coordinator reports `cloud_on_time` and
`device_on_time` separately and its comment says combining them is a policy choice belonging in the
arm. `device_on_time` is counted BESIDE the numerator and never added to it: the device always has
an answer (D19, D87), so an OR-combined target is met by construction on every opportunity the
device answers in time and the shortfall would be structurally near zero. Measured on the committed
`covex-v6-state_n16_s5` cell: the alert type's on-time CLOUD fraction is 0.2089, below its 0.25
target, while every one of its 11,769 instants has a device answer. An OR feed cannot see the one
deficit this rung exists to act on.

THREE TARGETS, THREE DIFFERENT DENOMINATORS (D178 (1)), each CHECKED against committed cells rather
than assumed. The numbers below are from that same committed cell.

  alert       unit = the device's EPISODE. Denominator = NINETEEN decision instants, a DECLARED
              CONSTANT, not a count. An episode is the append-only EP-G context of D148 with a
              21-frame cap, and D153's floor makes instants before the episode's third frame not
              decision instants for any arm, so an episode's decision instants are positions 2 to
              20 inclusive: NINETEEN, not 18 and not 21. VERIFIED: 714 episodes, instants per
              episode min 2, median 19, max 19, and the short ones are a play ending mid-episode.
              THE BIAS OF THE CONSTANT IS MEASURED, NOT ASSUMED. About 27 percent of episodes are
              truncated by a play ending, and giving those 19 instants overstates their shortfall.
              True per-episode denominators give a type shortfall of 0.1427 and the flat 19 over
              the same episodes gives 0.1467, so the constant costs +0.0040 on the shortfall.
              WHY PER EPISODE AND NOT POOLED, measured rather than argued: the mean per-episode
              shortfall is 0.1427 and the POOLED shortfall over all 11,769 instants is 0.0411.
              Pooling understates the alert deficit by 3.5x, because 486 of 714 episodes are below
              target while the type as a whole is only just below it. That is consistency check 3's
              "a real effect averaged into undetectability".
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
difference is large on a single device. The traced unit is robo001 on the committed seed-5 cell:
SIX offered opportunities, of which FOUR are one question re-asked, two were sent and one arrived
on time. The offline headline scores the same traffic as repeated measures WITHIN question,
clustered by question (D161), which is a different denominator on purpose. The online counter and
the offline score are therefore not the same quantity and must not be quoted against each other.

CLASSIFICATION IS BY DEVICE-ID PREFIX, NOT BY `kind`. The completion hook's `kind` is "monitor"
for alert and "recall" FOR BOTH recall AND assistance: on the committed cell every `asst00x`
completion arrives as kind "recall" with `deadline_s` 2.0, and every `robo00x` as kind "recall"
with 3.0. `arms_v6fair.py:129` maps kind monitor -> dashcam and EVERYTHING ELSE -> robot, which
merges assistance into recall. Prefix classification is `share_admission.type_of_device`, the same
function the consumers of these weights use, so the weights and the shares cannot disagree about
which type a device is.

HOW THE EPISODE IS IDENTIFIED. `rec["episode_id"]` from the completion hook is THE AUTHORITY
(addendum 12 item 3; the coordinator now carries `episode_id` and `episode_index`). The EP-G
prompt-token derivation this module used before the hook carried the field is KEPT as a
CROSS-CHECK, not as a fallback that silently takes over: both are computed, their agreement is
counted (`alert_episode_key_agree` against `alert_episode_key_disagree`), and the hook decides. The
derivation is exact where it applies - on the committed live cell all 8,312 dashcam requests
satisfy `(prompt_tokens - 42) % 338 == 0` with positions 2 to 20, zero violations - but it is blind
to an episode the policy never serves, 4 of 714 on that cell, and the hook is not.

THE WINDOW IS CUMULATIVE OVER THE RUN, deliberately and as the only option that adds no knob. A
sliding window would be a tuned parameter, and D151 (1)'s margin exists to stop the objective
acquiring tuned parameters. The consequence is that weights move fastest early and settle.

THE OPEN EPISODE IS EXCLUDED from a device's alert shortfall. A partial episode reads as a
shortfall whatever the policy does, because its instants have not all happened yet; counting it
would make the weight a function of where in its episode each device happens to be.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

import deficit_gain_d178 as GAIND
import share_admission as SA

# ---- D178 (1) targets. Per type, from the use case, NOT from any achieved result.
TARGETS: Dict[str, float] = {"alert": 0.25, "recall": 0.90, "assistance": 0.90}
TARGET_SOURCE = "D178 (1), spec v6 sections 2 and 8"
# The unit each target's denominator is counted over. Three targets, three denominators.
UNIT: Dict[str, str] = {"alert": "device-episode", "recall": "device", "assistance": "device"}

# ---- the EP-G episode geometry, from the trace generator's own frozen constants
EPG_CAP_FRAMES = 21                 # fleet/trace.py EPG_CAP_FRAMES (D148)
EPG_MIN_FRAMES = 3                  # fleet/trace.py EPG_MIN_FRAMES (D153)
EPG_FIRST_POS = EPG_MIN_FRAMES - 1  # 2: the first position that is a decision instant
EPG_LAST_POS = EPG_CAP_FRAMES - 1   # 20
# NINETEEN decision instants in a complete episode. Verified against the committed cell.
EPG_DECISION_INSTANTS = EPG_LAST_POS - EPG_FIRST_POS + 1
assert EPG_DECISION_INSTANTS == 19

# ---- the EP-G prompt-token law, bodies.epg_prompt_tokens; a CROSS-CHECK, not the authority
EPG_TEXT_TOKENS = 42
EPG_TOK_PER_FRAME = 338


def position_from_prompt_tokens(prompt_tokens: Any) -> Optional[int]:
    """The episode position of a monitor request, or None if the prompt does not follow the law.

    Exact where it applies, not a proxy: the law is `42 + 338 * n_frames` and the position is
    `n_frames - 1`. A prompt that does not satisfy it is NOT rounded to the nearest position,
    because a rounded position would silently invent an episode boundary.
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
    """One scored unit: a device's question stream. `offered` is the DENOMINATOR."""

    __slots__ = ("offered", "on_time")

    def __init__(self) -> None:
        self.offered = 0
        self.on_time = 0

    def shortfall(self, target: float) -> float:
        if self.offered <= 0:
            return 0.0
        return max(float(target) - self.on_time / self.offered, 0.0)


class _AlertDevice:
    """One alert device: the on-time count of each episode it has closed, plus the open one."""

    __slots__ = ("open_on_time", "epid", "last_pos", "seen", "closed")

    def __init__(self) -> None:
        self.open_on_time = 0
        self.epid: Optional[str] = None
        self.last_pos: Optional[int] = None
        self.seen: set = set()
        self.closed: List[int] = []


class DeficitFeed:
    """Per-device shortfalls, the per-device weights, and the per-type maxima the split needs.

    Three feeds in, two outputs out:

        observe_offered_instant(device_id, opportunity_id)   REPORTING ONLY, not a denominator
        observe_offered_question(device_id, query_id)        recall / assistance denominator
        observe_completion(...)                              every numerator

        weight_device(device_id)        -> the ORDERING consumer's input (the PRIMARY one)
        weights_by_type(pending)        -> the FLEXIBLE SPLIT consumer's input

    Nothing here reads a quality table or an accuracy value (D177 (2)).
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

    def devices(self) -> List[str]:
        return sorted(set(self._alert) | set(self._dev))

    # ---- the denominators --------------------------------------------------------------------
    def observe_offered_instant(self, device_id: Any, opportunity_id: Any) -> None:
        """One OFFERED alert decision instant. REPORTING ONLY: it is NOT in any denominator.

        Deduplicated by opportunity id, because the same instant is surfaced in the roster on every
        100 ms period until it resolves and a count of item-periods is not a count of instants (the
        confusion `share_capacity.py` records about `c5_dash_held`). It is kept because it is the
        one independent check on the episode count: on the dry seed-4 posted cell it reads 11,764,
        which is exactly the monitor opportunity count D174 (2) measured on the committed cells, so
        the offer stream the feed sees is the whole stream and not a sample.
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
                           episode_id: Any = None, episode_index: Any = None) -> None:
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
            self._alert_completion(str(device_id), ont, prompt_tokens, episode_id, episode_index)
        else:
            self._dev.setdefault(str(device_id), _Unit()).on_time += 1 if ont else 0

    def _alert_completion(self, device_id: str, on_time: bool, prompt_tokens: Any,
                          episode_id: Any, episode_index: Any) -> None:
        st = self._alert.setdefault(device_id, _AlertDevice())
        pos = position_from_prompt_tokens(prompt_tokens)
        if episode_id is not None:
            # THE AUTHORITY (addendum 12 item 3). The token-law position is still computed and
            # cross-checked against `episode_index` rather than thrown away, because two
            # derivations that agree is how this module's first version was caught being wrong.
            self._bump("alert_episode_key_from_record")
            boundary = st.epid is not None and st.epid != str(episode_id)
            st.epid = str(episode_id)
            if episode_index is not None and pos is not None:
                self._bump("alert_episode_key_agree" if int(episode_index) == pos
                           else "alert_episode_key_disagree")
            elif pos is None:
                self._bump("alert_pos_unparsable")
        elif pos is None:
            # no key at all: counted, never guessed at
            self._bump("alert_pos_unparsable")
            self._bump("alert_episode_key_absent")
            boundary = False
        else:
            # the hook did not carry the field: the derivation stands in, and says so
            self._bump("alert_episode_key_from_token_law")
            boundary = st.last_pos is not None and pos <= st.last_pos
        if pos is not None:
            st.last_pos = pos
        if boundary:
            st.closed.append(st.open_on_time)
            st.open_on_time = 0
            self._bump("alert_episodes_closed")
        st.open_on_time += 1 if on_time else 0

    # ---- the per-device output ----------------------------------------------------------------
    def shortfall_device(self, device_id: Any) -> float:
        """The device's own clipped shortfall, over its OWN unit (an episode mean for alert)."""
        did = str(device_id or "")
        t = self.type_of(did)
        if t is None:
            return 0.0
        target = TARGETS[t]
        if t == "alert":
            st = self._alert.get(did)
            if st is None or not st.closed:
                return 0.0
            vals = [max(target - ot / EPG_DECISION_INSTANTS, 0.0) for ot in st.closed]
            return sum(vals) / len(vals)
        u = self._dev.get(did)
        return u.shortfall(target) if u else 0.0

    def weight_device(self, device_id: Any) -> float:
        """`w_d = 1 + gain * (shortfall_d / target_d)`, floored at 1, in [1, 3] for every type."""
        t = self.type_of(device_id)
        if t is None:
            return 1.0
        return GAIND.weight(self.shortfall_device(device_id), TARGETS[t], self.gain)

    def weights_by_type(self, pending: Optional[Iterable[str]] = None) -> Dict[str, float]:
        """Per type, the MAXIMUM `w_d` over that type's devices WITH PENDING WORK (addendum 12 3b).

        The maximum, not the mean, because the split exists to get capacity to the device that is
        behind: averaging a deficit device against its satisfied peers is the "real effect averaged
        into undetectability" shape, and it is what the per-TYPE form of this feed did.

        A type with NO pending device gets 1.0, the minimum, so a type that is not competing does
        not hold a share it cannot use. `pending = None` means "every known device", which is the
        diagnostic reading and is never what the live consumer passes.
        """
        if pending is None:
            cand = self.devices()
        else:
            cand = [str(d) for d in pending if d is not None]
        out: Dict[str, float] = {}
        for t in SA.TYPES:
            ws = [self.weight_device(d) for d in cand if self.type_of(d) == t]
            out[t] = max(ws) if ws else 1.0
        return out

    # ---- diagnostics only --------------------------------------------------------------------
    def type_shortfall(self, qtype: str) -> float:
        """The MEAN over the type's units, kept as a DIAGNOSTIC (addendum 12 item 1).

        It is not read by either consumer. It is the quantity the per-type build of this module
        used, and it is reported so the two readings can be compared rather than confused.
        """
        t = TARGETS.get(qtype)
        if t is None:
            return 0.0
        if qtype == "alert":
            vals = [max(t - ot / EPG_DECISION_INSTANTS, 0.0)
                    for st in self._alert.values() for ot in st.closed]
        else:
            vals = [u.shortfall(t) for did, u in self._dev.items()
                    if self.type_of(did) == qtype and u.offered > 0]
        return (sum(vals) / len(vals)) if vals else 0.0

    def units(self, qtype: str) -> List[Tuple[int, int]]:
        """(offered, on_time) per scored unit of the type, for a distribution report."""
        if qtype == "alert":
            return [(EPG_DECISION_INSTANTS, ot)
                    for st in self._alert.values() for ot in st.closed]
        return [(u.offered, u.on_time) for did, u in sorted(self._dev.items())
                if self.type_of(did) == qtype and u.offered > 0]

    def as_dict(self, pending: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        self.counts["alert_episodes_open"] = sum(
            1 for st in self._alert.values() if st.last_pos is not None or st.epid is not None)
        devs = self.devices()
        return {
            "gain": self.gain, "gain_ruling": GAIND.GAIN_RULING, "form": GAIND.FORM,
            "targets": dict(TARGETS), "target_source": TARGET_SOURCE, "units": dict(UNIT),
            "currency": "on-time CLOUD answers only (D177, D178 (1)); device_on_time recorded, "
                        "never added to the numerator",
            "alert_decision_instants_per_episode": EPG_DECISION_INSTANTS,
            "n_offers": self.n_offers, "n_completions": self.n_completions,
            "per_device": {d: {"type": self.type_of(d),
                               "shortfall": round(self.shortfall_device(d), 6),
                               "weight": round(self.weight_device(d), 6),
                               "episodes_closed": (len(self._alert[d].closed)
                                                   if d in self._alert else None),
                               "offered": self._dev[d].offered if d in self._dev else None,
                               "cloud_on_time": self._dev[d].on_time if d in self._dev else None}
                           for d in devs},
            "weights_by_type_over_all_devices": {k: round(v, 6)
                                                 for k, v in self.weights_by_type().items()},
            "weights_by_type_pending": ({k: round(v, 6)
                                         for k, v in self.weights_by_type(pending).items()}
                                        if pending is not None else None),
            "type_shortfall_DIAGNOSTIC_ONLY": {t: round(self.type_shortfall(t), 6)
                                               for t in SA.TYPES},
            "n_units": {t: len(self.units(t)) for t in SA.TYPES},
            "counts": dict(sorted(self.counts.items())),
        }
