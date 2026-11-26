#!/usr/bin/env python3
"""covex-v6-fair as D177 (2) leaves it: THE DEFICIT FEED ONLY, on EITHER rung-2 base.

    rung 2 (covex-v6-state-shares OR covex-v6-state-uo-c5attr)
      + DEFICIT FEED   per-type shortfalls against the D178 (1) targets, each over its OWN
                       denominator, turned into w_t = 1 + 2.0 * shortfall_t, floored at 1
      - VALUE READER   REMOVED (D177 (2)); the quality table is reporting only and no accuracy
                       number is read anywhere on this path

WHY THIS IS A NEW MODULE AND NOT A FLAG ON `arms_v6fair.py`. `arms_v6fair.V6FairArm` is the
pre-D177 rung 3: it declares `value_reader=True`, it builds on `covex-v6-state` rather than on a
rung-2 base with D179 share admission, it classifies assistance as recall (`arms_v6fair.py:129`
maps every non-monitor kind to "robot", and on the committed cells every `asst00x` completion
arrives as kind "recall"), and it feeds `cf_objective.DeficitCounters`, whose targets are one
per-device 0.90 for all three types with no per-episode reset and whose gain is the module default
1.0. Each of those is something D177 or D178 changed. Editing it in place would also rewrite the
meaning of a name that `arm_names_v6` already describes. So this is a separate module and a
separate family of names, and `arms_v6fair` is left exactly as committed.

THE BASE IS A PARAMETER, BECAUSE WHICH RUNG 2 IS RUNG 2 IS NOT YET DECIDED. The user's addendum 9
item A fixes the contingency: rung 2 will be `covex-v6-state-shares` if it passes all three D179
(6) pre-registered checks, and `covex-v6-state-uo-c5attr` as a logged override if shares fails any
of them. Both variants are registered here under their own names, so the choice is made AT CELL
TIME by picking the name, and nothing in this module has to change either way. Hardwiring one base
would have meant a code edit between the check and the cell, which is the shape D172 (2) forbids.

ONE CONSEQUENCE OF THE CONTINGENCY. CORRECTED 2026-11-23: THE PARAGRAPH THAT STOOD HERE WAS MADE
FALSE BY D182 AND IS NOW WRONG IN THE DIRECTION THAT UNDERSTATES THIS ARM. It said the weights
have NO READER AT ALL on the c5attr base and that the feed is an ABSENT LINK there. That was true
when the only consumer was the flexible split, and D182 added a SECOND consumer: the ORDERING hook
`hybrid_arm._deficit_order_key`, consumed as the LEADING SORT KEY at hybrid/hybrid_arm.py:399, 483
and 486. Ordering does NOT go through share admission, so it fires on this base.

MEASURED, on a dry seed-4 cell, bare, and replicated independently by two other sessions to the
digit: gain 2.0 against the gain-0 control moves 4,512 decisions setwise, 12,272 positionally;
the ORDER-ONLY arm is BYTE-IDENTICAL to the both-consumers arm (12e4f73ce0ebd865 / 13,812) and
the SPLIT-ONLY arm moves EXACTLY ZERO (9a4be873eb3c5fba / 14,218, identical to the control). The
first difference is an ordering swap at index 1942, t = 207.1 s.

SO THE ACCURATE STATEMENT IS NARROWER THAN THE OLD ONE: on the c5attr base the FLEXIBLE-SPLIT
consumer is absent by construction, because `_share_ok` returns before `SA.allowed` when an arm
carries no share admission, and that is Rule 2's `unexpressible` rather than a null about the
policy. The ORDERING consumer is present, fires, and is the whole of rung 3's contribution on this
base. `covex-v6-fair-c5attr` therefore CAN be read as a test of the weighting, through ordering.

THE SWITCH IS AN ARM-SCOPED INSTANCE ATTRIBUTE, `live2_deficit_feed`, DEFAULT FALSE, and a truthy
CLASS attribute RAISES. Exactly the pattern `release_recheck.arm_enables` and
`share_admission.arm_enables` establish, and for the reason both of their docstrings record: a
class attribute turns the rung on for every arm that inherits it and makes the cells incomparable
(the D172 rung-2 note on `live2_belief_apply`), and a module global that defaulted ON once cost a
whole live cell here. A class default of FALSE is allowed through, because it cannot turn anything
on. The switch is set on every object the decide path can bind `self` to, through the base's own
`switch_targets()` walk where there is one.

WHAT IS NOT WIRED YET, SAID HERE RATHER THAN DISCOVERED IN A NULL. The coordinator's single
admission gate calls `SA.allowed(...)` WITHOUT `weights_by_type` (coordinator.py:1437 (origin/main)), so in a
run against the committed coordinator these weights are computed, exposed and NOT READ: the
flexible pool still splits equally. `live2_share_weights()` is the accessor the gate needs and the
one-line change is named in this build's report. Until that line lands, this feed is Rule 2's
UNEXPRESSIBLE category on both bases and no cell of it may be read as evidence about the policy.
The proofs in `d178_deficit_feed_proofs.py` therefore run the Step 2b comparison through an
explicitly declared PROOF-ONLY SHIM on `_share_ok`, and report the un-shimmed number beside it,
which is zero.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import arms_v6c5 as C5
import arms_v6shares as SH
import deficit_feed as DF
import deficit_gain_d178 as GAIND
import share_admission as SA

FAIRFEED_VERSION = "covex-v6-fair-feed-1.0"
SWITCH_ATTR = "live2_deficit_feed"

# The two rung-2 bases of the addendum 9 item A contingency, by the name each is registered under.
BASES: Dict[str, Any] = {
    "covex-v6-state-shares": SH.V6StateSharesArm,
    "covex-v6-state-uo-c5attr": C5.V6StateUoC5AttrArm,
}
# Which bases carry a reader for the weights. See the module docstring.
BASE_HAS_WEIGHT_READER = {"covex-v6-state-shares": True, "covex-v6-state-uo-c5attr": False}


class DeficitFeedSwitchError(RuntimeError):
    """Raised when the switch is set in a way that could turn the rung on for every arm."""


def arm_enables(arm: Any) -> bool:
    """Read `live2_deficit_feed` from the ARM INSTANCE only. Default False; a class-level ON RAISES.

    Same strictness, and the same words, as `release_recheck.arm_enables` and
    `share_admission.arm_enables`. `getattr` would read a class attribute as though the instance
    had declared it, which is how one switch turns a rung on for every arm in a run.
    """
    try:
        own = vars(arm)
    except TypeError:                                                       # pragma: no cover
        own = {}
    if SWITCH_ATTR not in own:
        for klass in type(arm).__mro__:
            if bool(klass.__dict__.get(SWITCH_ATTR, False)):
                raise DeficitFeedSwitchError(
                    "%s is ON as a CLASS attribute of %s and the instance declares nothing. "
                    "D178 (2) and the addendum require an arm-scoped INSTANCE attribute: a "
                    "class-level switch turns this rung on for every arm that inherits it and "
                    "makes the cells incomparable." % (SWITCH_ATTR, klass.__name__))
        return False
    return bool(own[SWITCH_ATTR])


class DeficitFeedMixin:
    """The feed, over whichever rung-2 base it is mixed into.

    Three hooks in, one accessor out:

        live2_roster      OFFERED alert decision instants (the per-episode denominator)
        decide            OFFERED recall and assistance questions (the per-device denominators)
        live2_completed   the numerator: ON-TIME CLOUD answers only (D177, D178 (1))
        live2_share_weights()   the ONE output, for SA.allowed(weights_by_type=...)
    """

    _fairfeed_base_name = ""

    def _fairfeed_init(self, *, deficit_feed: bool, gain: float,
                       ordering: bool = True, split: bool = True) -> None:
        self.arm_version = FAIRFEED_VERSION
        self._feed = DF.DeficitFeed(gain=float(gain))
        self._feed_gain = float(gain)
        # the TWO CONSUMERS, each switchable ALONE, because addendum 12 item 5 requires the Step 2b
        # count to be ATTRIBUTABLE: "a combined count that cannot be attributed is not a pass".
        # One-factor arms are the only way to say which consumer moved a decision.
        self._feed_ordering = bool(ordering)
        self._feed_split = bool(split)
        self._fairfeed_pending: Dict[str, set] = {"alert": set(), "recall": set(),
                                                  "assistance": set()}
        # the SWITCH, on the instance, and on every object the decide path can bind `self` to
        targets = self._fairfeed_targets()
        for obj in targets:
            try:
                object.__setattr__(obj, SWITCH_ATTR, bool(deficit_feed))
            except Exception:                                              # noqa: BLE001
                setattr(obj, SWITCH_ATTR, bool(deficit_feed))
        # read back through the strict reader, so a construction that did not take RAISES here
        self._feed_on = arm_enables(self)
        if self._feed_on != bool(deficit_feed):                            # pragma: no cover
            raise DeficitFeedSwitchError(
                "%s did not take on the instance of %s" % (SWITCH_ATTR, type(self).__name__))
        self._install_ordering_override()

    # ---- consumer 1 (the PRIMARY one): ORDERING ----------------------------------------------
    def _install_ordering_override(self) -> None:
        """Bind `_deficit_order_key` ON THE HYBRID CORE INSTANCE, never on a class.

        The hook is defined on `HybridArm` with a neutral 0.0 default and is called as
        `self._deficit_order_key(...)` from the two deadline-ordering sites, where `self` is the
        INNER HybridArm object and not this wrapper. So the override has to live on that object, or
        it is never consulted: this is the three-object-chain lesson `arms_v6c5.py` records, from
        the other direction. It is set as an INSTANCE attribute shadowing the class method, so no
        other arm in the process can inherit it, and a plain function is bound rather than a method
        so the instance-attribute call passes no `self`.
        """
        core = None
        for obj in reversed(self._fairfeed_targets()):
            if hasattr(type(obj), "_deficit_order_key"):
                core = obj
                break
        self._fairfeed_order_core = core
        if core is None:                                                   # pragma: no cover
            self._feed._bump("order_hook_absent_on_chain")
            return
        if not (self._feed_on and self._feed_ordering):
            # leave the frozen neutral default in place; nothing is shadowed at all
            return
        feed = self._feed
        counts = self._feed.counts
        resolve = self._fairfeed_resolve_device

        def _key(device_id: Any, kind: Any) -> float:
            did = resolve(device_id, kind)
            if did is None:
                counts["order_key_unresolved_device"] = \
                    counts.get("order_key_unresolved_device", 0) + 1
                return 0.0
            counts["order_key_resolved"] = counts.get("order_key_resolved", 0) + 1
            # NEGATIVE, so a LARGER w_d sorts FIRST under an ascending sort (addendum 12 item 3a)
            return -float(feed.weight_device(did))

        object.__setattr__(core, "_deficit_order_key", _key)

    def _fairfeed_resolve_device(self, device_id: Any, kind: Any) -> Optional[str]:
        """The device this ordering item belongs to, or None rather than a guess.

        THE ARGUMENT IS NOT ALWAYS A DEVICE ID, and that is measured, not assumed: on the committed
        `hybrid_arm.py` the three call sites pass `getattr(<frozen dataclass>, "device_id", None)`,
        and neither `interface.EpisodicStream` nor `interface.RecallQuery` HAS that field, so every
        one of 10,956 calls in a 180 s dry cell receives None. The one-line fix in `hybrid_arm.py`
        is named in this build's report; until it lands, an unresolved item is COUNTED and takes
        the neutral 0.0, so the ordering collapses to the frozen order rather than to an invented
        one. This resolver therefore accepts a device id, a dashcam stream id (which IS the device
        id: the roster's `sh_instant` is keyed by exactly `dash000` to `dash005` and `hybrid_arm`
        looks items up in it by `stream_id`), or a session id (mapped through the roster's
        `session_device`), and returns None for anything else.
        """
        if device_id is None:
            return None
        s = str(device_id)
        if DF.DeficitFeed.type_of(s) is not None and "|" not in s:
            return s
        sd = getattr(self, "_fairfeed_session_device", None) or {}
        got = sd.get(s)
        return str(got) if got else None

    # ---- consumer 2: the FLEXIBLE SPLIT -------------------------------------------------------
    def live2_share_weights(self) -> Optional[Dict[str, float]]:
        """Per type, the MAXIMUM `w_d` over that type's devices with PENDING WORK, or None.

        None, not a dict of ones: `SA.allowed` treats a falsy `weights_by_type` as "split equally"
        and so takes the identical branch, and returning None makes the OFF arm's behaviour a
        property of this one line instead of of floating-point equality. The same is true of the
        split-off ablation, which is why it returns None too rather than a neutral dict.
        """
        if not (getattr(self, "_feed_on", False) and getattr(self, "_feed_split", False)):
            return None
        pend = set()
        for s in self._fairfeed_pending.values():
            pend |= s
        return self._feed.weights_by_type(pend)

    def deficit_feed_report(self) -> Dict[str, Any]:
        pend = set()
        for s in (getattr(self, "_fairfeed_pending", None) or {}).values():
            pend |= s
        d = dict(self._feed.as_dict(pending=pend))
        d["switch"] = {"name": SWITCH_ATTR, "on": bool(getattr(self, "_feed_on", False)),
                       "scope": "arm instance", "chain": self._fairfeed_switch_chain()}
        d["consumers"] = {
            "ordering": {"on": bool(getattr(self, "_feed_ordering", False)),
                         "hook": "hybrid/hybrid_arm.py _deficit_order_key, overridden on the "
                                 "INNER HybridArm instance",
                         "installed_on": (type(getattr(self, "_fairfeed_order_core", None))
                                          .__name__),
                         "shadowed": ("_deficit_order_key" in
                                      vars(getattr(self, "_fairfeed_order_core", None) or object()))},
            "flexible_split": {"on": bool(getattr(self, "_feed_split", False)),
                               "read": "share_admission.py:162-168 via "
                                       "coordinator SA.allowed(weights_by_type=)",
                               "weights_now": self.live2_share_weights()}}
        d["base"] = self._fairfeed_base_name
        d["weights_have_a_reader"] = bool(
            BASE_HAS_WEIGHT_READER.get(self._fairfeed_base_name, False))
        return d

    def _fairfeed_targets(self) -> List[Any]:
        """Every object the decide path can bind `self` to: this wrapper and its delegation chain.

        The shares base publishes the walk as `switch_targets()`; the c5attr base does not, so the
        chain is walked the same way here rather than left at the wrapper. Setting only the
        wrapper is how a switch reads as live and is not (`arms_v6shares.py`'s own note).
        """
        walk = getattr(self, "switch_targets", None)
        if callable(walk):
            return list(walk())
        out: List[Any] = []
        o: Any = self
        seen = set()
        while o is not None and id(o) not in seen:
            seen.add(id(o))
            out.append(o)
            o = o.__dict__.get("_rules") or o.__dict__.get("_base")
        return out

    def _fairfeed_switch_chain(self) -> List[bool]:
        return [bool(vars(o).get(SWITCH_ATTR, False)) for o in self._fairfeed_targets()]

    # ---- the three feeds ---------------------------------------------------------------------
    def live2_roster(self, roster: Dict[str, Any]) -> None:
        if getattr(self, "_feed_on", False):
            self._fairfeed_session_device = dict(roster.get("session_device") or {})
            # PENDING ALERT WORK is the set of devices with a monitor instant currently OFFERED,
            # which is exactly what `sh_instant` holds. Not "every alert device": a standing
            # stream is not pending work, and a type that is not competing must not hold a share
            # it cannot use (addendum 12 item 3b).
            pend = set()
            for did, inst in (roster.get("sh_instant") or {}).items():
                self._feed.observe_offered_instant(did, (inst or {}).get("opportunity_id"))
                if DF.DeficitFeed.type_of(did) == "alert":
                    pend.add(str(did))
            self._fairfeed_pending["alert"] = pend
        return super().live2_roster(roster)                                # type: ignore[misc]

    def decide(self, obs: Any) -> Any:
        if getattr(self, "_feed_on", False):
            sd = getattr(self, "_fairfeed_session_device", None) or {}
            pend: Dict[str, set] = {"recall": set(), "assistance": set()}
            for q in (getattr(obs, "recall", None) or ()):
                did = sd.get(getattr(q, "session_id", None))
                if did is None:
                    self._feed._bump("question_offer_no_device")
                    continue
                self._feed.observe_offered_question(did, getattr(q, "query_id", None))
                t = DF.DeficitFeed.type_of(did)
                if t in pend:
                    pend[t].add(str(did))
            self._fairfeed_pending["recall"] = pend["recall"]
            self._fairfeed_pending["assistance"] = pend["assistance"]
        return super().decide(obs)                                         # type: ignore[misc]

    def live2_completed(self, rec: Dict[str, Any]) -> None:
        # q4: the in-run cold-fraction estimator learns from THIS arm's own completions. One memoised
        # instance lookup when off.
        import q4_avoided_rebuild as _Q4                                       # noqa: PLC0415
        if _Q4.enabled_cached(self):
            _Q4.observe(self, rec)
        if getattr(self, "_feed_on", False):
            self._feed.observe_completion(
                device_id=rec.get("device_id"), kind=rec.get("kind"),
                cloud_on_time=rec.get("cloud_on_time"),
                device_on_time=rec.get("device_on_time"),
                prompt_tokens=rec.get("prompt_tokens"),
                episode_id=rec.get("episode_id"),
                episode_index=rec.get("episode_index"))
            n = int(self.stats.get("deficit_feed_completions", 0)) + 1
            self.stats["deficit_feed_completions"] = n
            # the arm_stats block a cell reader takes, refreshed periodically rather than on every
            # completion: `as_dict` walks every scored unit, and at about 12,000 completions per
            # cell a per-completion refresh is quadratic in the episode count for no new reader.
            if n % 250 == 0:
                self.stats["deficit_feed"] = self._feed.as_dict()
        # DELEGATE TO `_rules`, NOT THROUGH `super()`. The base chain does not DEFINE
        # `live2_completed` at any level above the inner HybridArm: V6StateArm reaches it through
        # its own `__getattr__`, and a `super()` lookup does not consult an instance's
        # `__getattr__`, so `getattr(super(), "live2_completed", None)` silently returns None and
        # the inner arm never hears a completion. That would drop the C2 throttle's release
        # bookkeeping and the c5attr base's whole attribution signal, and it would show up only as
        # the OFF arm failing to collapse. `arms_v6fair.py:101` delegates the same way.
        inner = getattr(self._rules, "live2_completed", None)
        if callable(inner):
            inner(rec)

    def live2_describe(self) -> Dict[str, Any]:
        d = dict(super().live2_describe())                                 # type: ignore[misc]
        d.update(arm=self.name, arm_version=FAIRFEED_VERSION,
                 covex_v6_fair_feed=dict(
                     rung=3, rules_base=self._fairfeed_base_name,
                     switch=SWITCH_ATTR, switch_on=bool(getattr(self, "_feed_on", False)),
                     switch_chain=self._fairfeed_switch_chain(),
                     gain=self._feed_gain, gain_declared=GAIND.GAIN,
                     gain_ruling=GAIND.GAIN_RULING, gain_source=GAIND.GAIN_SOURCE,
                     value_reader="REMOVED (D177 (2)); no accuracy value is read on this path",
                     currency="on-time CLOUD answers only (D177, D178 (1))",
                     targets=dict(DF.TARGETS), units=dict(DF.UNIT),
                     alert_decision_instants_per_episode=DF.EPG_DECISION_INSTANTS,
                     consumers=dict(
                         ordering=dict(
                             on=bool(getattr(self, "_feed_ordering", False)),
                             role="PRIMARY (addendum 12 item 3a)",
                             read="hybrid/hybrid_arm.py `_deficit_order_key`, the first key at "
                                  "both deadline-ordering sites; overridden on the INNER "
                                  "HybridArm instance to return the NEGATIVE w_d",
                             known_gap=("the committed call sites pass getattr(<frozen "
                                        "dataclass>, 'device_id', None) and neither "
                                        "EpisodicStream nor RecallQuery has that field, so every "
                                        "call receives None and an unresolved item takes the "
                                        "neutral 0.0; see order_key_unresolved_device")),
                         flexible_split=dict(
                             on=bool(getattr(self, "_feed_split", False)),
                             read="share_admission.py:162-168 via the coordinator's "
                                  "SA.allowed(weights_by_type=) call site",
                             rule="per type, the MAXIMUM w_d over that type's devices with "
                                  "pending work; 1.0 for a type with none",
                             weighted="the FLEXIBLE pool only; floors, W_max and the oversize "
                                      "rule are UNCHANGED (D179 intact)")),
                     consumer_wired=bool(
                         BASE_HAS_WEIGHT_READER.get(self._fairfeed_base_name, False))))
        return d


def make_class(base_name: str) -> Any:
    """The arm class for one rung-2 base. The base is a PARAMETER, never hardwired."""
    base = BASES[base_name]
    ns = {"_fairfeed_base_name": base_name}
    return type("V6FairFeed_" + base_name.replace("-", "_"), (DeficitFeedMixin, base), ns)


_CLASSES = {b: make_class(b) for b in BASES}


def make(name: str, base_name: str, *, deficit_feed: bool = True,
         gain: float = GAIND.GAIN, ordering: bool = True, split: bool = True,
         **kw: Any) -> Any:
    cls = _CLASSES[base_name]
    arm = cls(name=name, **kw)
    arm._fairfeed_init(deficit_feed=deficit_feed, gain=gain,
                       ordering=ordering, split=split)
    return arm


# Names. The base is chosen by picking the name AT CELL TIME (addendum 9 item A).
V6FAIRFEED_ARMS: Dict[str, Any] = {}
for _b, _tag in (("covex-v6-state-shares", "shares"), ("covex-v6-state-uo-c5attr", "c5attr")):
    _n = "covex-v6-fair-" + _tag
    V6FAIRFEED_ARMS[_n] = (
        lambda _b=_b, _n=_n, **kw: make(_n, _b, **kw))
    # CLAUDE.md Step 4, part one: the SWITCH off must collapse to the rung-2 base byte-identically
    V6FAIRFEED_ARMS[_n + "-off"] = (
        lambda _b=_b, _n=_n, **kw: make(_n + "-off", _b, deficit_feed=False, **kw))
    # CLAUDE.md Step 4, part two, and the addendum 12 item 5 COMPARATOR: the mechanism disabled at
    # gain 0, with the switch and BOTH consumers still ON, so every weight is exactly 1.0 and the
    # arm must collapse to the base as well. This is the stronger control of the two: it leaves
    # every hook, every counter and every code path live and removes only the quantity under test.
    V6FAIRFEED_ARMS[_n + "-gain0"] = (
        lambda _b=_b, _n=_n, **kw: make(_n + "-gain0", _b,
                                        gain=GAIND.NEGATIVE_CONTROL_GAIN, **kw))
    # ONE-FACTOR CONSUMER ABLATIONS. Addendum 12 item 5 requires the Step 2b count to be
    # ATTRIBUTABLE to a consumer, and "a combined count that cannot be attributed is not a pass".
    # These two arms are the only way to say which consumer moved a decision: each is the full
    # rung-3 arm with ONE consumer disabled, so the difference against gain 0 is that consumer's
    # alone. They are named so the attribution is a cell and not a code edit.
    V6FAIRFEED_ARMS[_n + "-orderonly"] = (
        lambda _b=_b, _n=_n, **kw: make(_n + "-orderonly", _b, split=False, **kw))
    V6FAIRFEED_ARMS[_n + "-splitonly"] = (
        lambda _b=_b, _n=_n, **kw: make(_n + "-splitonly", _b, ordering=False, **kw))


def register() -> None:
    import arms as A
    SH.register()
    C5.register()
    A.ARMS.update(V6FAIRFEED_ARMS)
