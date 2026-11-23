#!/usr/bin/env python3
"""THE OBJECTIVE the v5 counterfactual maximises, with per-device deficit weighting and harm to
other devices (D151 (4), D149 (1), D152 (1) as amended by D155 (3), RECAST BY D177 (1)). CPU only.

THE CURRENCY IS EXPECTED ON-TIME CLOUD ANSWERS (D177 (1)), and this module and
`cf_planner.plan_state` were converted in ONE commit, for the reason recorded under
`CURRENCY_FLIP_STATUS`: converting either side alone subtracts on-time-unit harm from
correctness-unit gain.

    V = sum over devices i of  w_i * E[on-time CLOUD answers]  minus harm

and for one robot question with a cloud option `o`:

    V_i(o)      = w_i * P(o on time)
    V_i(DEVICE) = 0            (a device answer is not a CLOUD answer; it is the incumbent)
    harm        = sum over other devices j of  w_j * ( P_j(before this option) - P_j(after) )
    objective   = V_i(o) - harm

    w_d         = 1 + 2.0 * shortfall_d / target_d, floored at 1 (D185), supplied by the live
                  deficit feed (`live2/deficit_feed.py`, `deficit_gain_d178.GAIN = 2.0`) at the
                  rungs that feed it; `DeficitCounters` below is the v5 fallback and keeps its
                  own declared form, `1 + DEFICIT_GAIN * shortfall`, which is 1.0 for every
                  device whose counter is never fed
    margin      = w_d * MARGIN_CF with MARGIN_CF = 0.65824 ON-TIME ANSWERS (D177 (3),
                  `attainment_margin`, read through `cf_planner._margin`)

WHY THERE IS NO ACCURACY FACTOR LEFT IN A VALUE. At runtime there is no ground truth, so no
decision compares two answers' chances of being correct; the cloud with full evidence is more
accurate than the device on all three query types (measured), so within a type the accuracy
difference is a positive constant that never changes a decision. Correctness is the OUTCOME,
measured OFFLINE (D177 (1)), and the quality table is REPORTING ONLY (D177 (2)). The accuracy
arguments of `option_value`, `harm_to_others` and `harm_warm_from_queue_delay` are therefore
still accepted, still reported, and NO LONGER READ BY ANY VALUE. They are kept rather than
deleted so that no caller's signature changes in the same commit as the currency, and each one
says so at its own definition. The one case where the cloud was NOT more accurate is the
recent-frames ban, which stays as an IMPOSED RULE in `cf_planner` (D152 (2), D155 (4)) and not as
an accuracy number.

THREE THINGS IN THAT FORMULA ARE RULINGS AND NOT ARITHMETIC, so they are named here.

1. D155 (3) AMENDS THE HEADLINE TO "BY THE DEADLINE FROM EITHER SOURCE". A device answer counts
   only if it arrives within the deadline, so the device is no longer a free incumbent worth
   `1.0 * acc(dev)`: it carries its own delivery probability. `v5/value_readers.py`'s grid still
   prices the device at `p_on_time = 1.0`, which was right under D152 (1) and is not right under
   D155 (3). That module is not this session's and the difference is reported, not edited.

   MEASURED CONSEQUENCE IN THIS BUILD, and it is a CONSTANT, which CLAUDE.md Step 2 treats as a
   stopping condition for the link it implements: the only committed device-answer latency is
   `fleet/data_sources.py::DEVICE_WAIT_RULE_S = 0.567`, labelled `proxy-0.567` by D154 (5), and
   D155 (1) rules the StudyORIN-REC part 1 latencies (TTFT 3.3 s, e2e 6.65 s) an API artifact of
   the cold re-send path that must NOT be wired. 0.567 s is inside every robot deadline under
   test (2.5 to 5 s), so `P(device on time) = 1.0` for every robot question and D155 (3)'s
   restriction on the DEVICE side cannot change any decision in this build. It is implemented, it
   is read, and it is CONSTANT. The remedy is the measured warm-path per-question latencies
   D155 (1) says are being produced; until they land, every report must say that the "by the
   deadline" amendment is live on the cloud side and inert on the device side.

2. THE DEFICIT WEIGHT AND THE OBJECTIVE NOW STEER ON THE SAME QUANTITY, which CLOSES gap G14
   (spec v5 section 7.7). It was open because D152 (1) keeps the counters on observable on-time
   while the objective scored expected CORRECTNESS, so the weight and the quantity it multiplied
   were in different currencies and the mismatch was LOCATED rather than smoothed. D177 (1) puts
   the objective in on-time units too, so `w_i` is computed from observed on-time outcomes and
   multiplies an expected on-time count. The gap is not closed by a conversion invented here: it
   is closed by the ruling that the policy's currency is the one thing the counters can observe.

   The geometry that follows matters more than the statement, and it is proved in
   `weight_is_within_device_invariant`: `w_i` is a per-device scalar, so inside ONE device's
   candidate set it multiplies every candidate equally and CANNOT change which representation is
   chosen. If a report claimed the deficit weighting changes representation decisions, it would
   be claiming something this algebra forbids: that is CLAUDE.md Rule 2's `cancelled by geometry`
   and it is why the characteristic decision of the weighting is a CROSS-DEVICE one. The
   weighting acts, and acts only, where devices compete: the harm term of a request decision,
   warm and keep selection, shedding, and backlog order.

3. "HARM TO OTHERS" IS A DIFFERENCE OF TWO SIMULATED QUEUES, not a penalty term. It is
   `cf_cost.plan_queue` run without the option and again with it, with every other device's
   delivery probability re-predicted, so displacement is counted in the same units as the gain
   and no coefficient trades them off.

WHAT THE COUNTERS ARE NOT. They are not `arms_policy.Params.deficit_update` (the v1 artefact at
`arms_policy.py:276`, DEFAULT OFF, whose `w = 1` for every task and whose scaling B2 is
pre-registered and unimplemented). That one lives in the frozen policy library, is off in every
committed cell, and steers a different objective. This is a fresh implementation for v5 and it
does not import it.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
for _p in (str(HERE), str(REPO / "experiments/orchestration/live2"),
           str(REPO / "experiments/orchestration/live2/fleet")):
    if _p not in sys.path:
        sys.path.append(_p)

import cf_cost as CC                                                           # noqa: E402

# ---------------------------------------------------------------------------
# THE MEASURED DEVICE-ANSWER LATENCY (D171 (3)). The 0.567 s proxy is GONE from the decision
# path: this reads the same three measured Orin tables the coordinator's live device wait reads
# (`coordinator.py::_device_wait_s`, :764 dashcam, :780 robot, :785 single-shot), through the same
# `fleet/data_sources.py` accessors, so the counterfactual's device model and the live wait cannot
# drift apart. Per TYPE and, for dashcam, per EPISODE POSITION, because the three tables are three
# different measurements and none of them covers another's ids.
#
# WHAT THE MEASURED TABLES DO AND DO NOT MAKE VARY, which a report must not get wrong:
#   robot       0.2503 to 0.3108 s over 97 LH-REQ questions (StudyORIN-REC WARM, completion).
#               Every value is inside every robot deadline under test (2.5 to 5 s), so
#               `p_device_on_time` is still 1.0 on EVERY robot decision. It is now CONSTANT
#               BECAUSE THE DEVICE IS FAST, which is a measured fact, and no longer constant
#               because the input was a flat proxy, which was an artefact. The two look the same
#               in the output and are not the same claim.
#   single_shot 1,042 questions (StudySS2, completion, D146 (1)): realworldqa p50 0.9592 s,
#               refspatial p50 1.9947 s and max 3.4093 s against a 2.0 s deadline. HERE the term
#               varies, and 45.5 percent of refspatial questions give p_device_on_time = 0.
#   dashcam     EP-G warm APPEND first token by episode frame position, 0.2349 to 0.3169 s over
#               positions 1 to 21 (StudySH-EP, D146 (1) allows first token for a Yes/No alert).
#               Inside a 1 s dashcam deadline at every position; the EPISODE START curve is the
#               one that reaches 1.88 s.
# So the mechanism is LIVE and it is UNEXERCISED on the robot decisions the counterfactual makes
# in today's cells (CLAUDE.md Rule 2), which is a different sentence from "constant" and is the
# one that is true.
DEVICE_WAIT_FALLBACK_S = 0.567
DEVICE_WAIT_FALLBACK_NOTE = (
    "the superseded proxy-0.567 literal (D154 (5)), kept ONLY as the value counted when a lookup "
    "finds no measured entry. D171 (3) requires that counter to be 0: a non-zero fallback means "
    "the counterfactual priced a device answer on a number no one measured")


class DeviceLatency:
    """The measured per-type device-answer latency, with a fallback COUNTER rather than a silence.

    Mirrors `coordinator.py::_device_wait_s` lookup for lookup. Counts by type, and counts the
    fallback by WHY it was reached, because a missing dashcam table and a question id absent from
    the single-shot table need different remedies and only one of them is a missing measurement.
    """

    def __init__(self) -> None:
        self._robot: Optional[Dict[str, float]] = None
        self._ss: Optional[Dict[str, float]] = None
        self._dash: Optional[Dict[int, float]] = None
        self.counts: Dict[str, int] = {}

    def _bump(self, k: str) -> None:
        self.counts[k] = self.counts.get(k, 0) + 1

    def _tables(self) -> None:
        if self._robot is not None:
            return
        try:
            import data_sources as _DS                                         # noqa: PLC0415
            self._robot = {str(k): float(v) for k, v in _DS.device_recall_warm_latency_s().items()}
            self._ss = {str(k): float(v) for k, v in _DS.single_shot_total_s().items()}
            self._dash = {int(k): float(v) for k, v in _DS.dashcam_append_ttft_s().items()}
        except Exception:                                                      # noqa: BLE001
            self._robot, self._ss, self._dash = {}, {}, {}

    def wait_s(self, *, kind: str = "robot", question_id: Optional[str] = None,
               episode_frames: Optional[int] = None) -> float:
        self._tables()
        if kind in ("dashcam", "monitor"):
            tab = self._dash or {}
            if tab:
                n = int(episode_frames or 1)
                n = min(max(n, min(tab)), max(tab))
                self._bump("measured_dashcam")
                return float(tab[n])
            self._bump("fallback_no_dashcam_table")
            return DEVICE_WAIT_FALLBACK_S
        if question_id is not None:
            qid = str(question_id)
            v = (self._robot or {}).get(qid)
            if v is not None:
                self._bump("measured_robot")
                return float(v)
            v = (self._ss or {}).get(qid)
            if v is not None:
                self._bump("measured_single_shot")
                return float(v)
            self._bump("fallback_question_id_not_in_any_table")
            return DEVICE_WAIT_FALLBACK_S
        self._bump("fallback_no_question_id")
        return DEVICE_WAIT_FALLBACK_S

    def as_dict(self) -> Dict[str, Any]:
        self._tables()
        n_fb = sum(v for k, v in self.counts.items() if k.startswith("fallback"))
        return {"source": DEVICE_LATENCY_SOURCE,
                "n_robot": len(self._robot or {}), "n_single_shot": len(self._ss or {}),
                "n_dashcam_positions": len(self._dash or {}),
                "counts": dict(sorted(self.counts.items())),
                "n_fallback": n_fb, "fallback_is_zero": n_fb == 0,
                "fallback_s": DEVICE_WAIT_FALLBACK_S,
                "fallback_note": DEVICE_WAIT_FALLBACK_NOTE}


DEVICE_LATENCY_SOURCE = (
    "results/device/study_devlat/orin_device_latency_tables.json via fleet/data_sources.py "
    "(device_recall_warm_latency_s, single_shot_total_s, dashcam_append_ttft_s) - the SAME "
    "accessors coordinator.py::_device_wait_s reads")
DEVICE_ANSWER_LABEL = "measured-orin (D171 (3)); the proxy-0.567 literal is no longer on this path"

DEVLAT = DeviceLatency()

# The on-time target the deficit counters measure a shortfall against. It is the committed robot
# SLO (D133: p 0.90 within the deadline), per type, and it is DECLARED, not fitted.
ON_TIME_TARGET: Dict[str, float] = {"robot": 0.90, "dashcam": 0.90, "single_shot": 0.90}
ON_TIME_TARGET_SOURCE = "D133 robot headline: p 0.90 within the deadline, applied per type"

# The gain that turns a shortfall into a weight. DECLARED, never swept: a swept gain would be a
# tuned objective, which is the thing D151 (1)'s margin exists to prevent.
DEFICIT_GAIN = 1.0

OBJECTIVE_STATEMENT = (
    "deficit-weighted expected ON-TIME CLOUD ANSWERS, minus the on-time cloud answers other "
    "devices lose (D177 (1), D191 (1); D151 (4), D152 (1), D155 (3) for the deadline and the "
    "weighting); correctness is the OUTCOME, measured offline, and the quality table is "
    "reporting only (D177 (2))")


# ---------------------------------------------------------------------------
# Deficit counters: observable on-time only


@dataclass
class DeviceDeficit:
    device_id: str
    kind: str = "robot"
    served: int = 0
    on_time: int = 0

    @property
    def rate(self) -> float:
        return (self.on_time / self.served) if self.served else 1.0

    def shortfall(self, target: Optional[float] = None) -> float:
        t = ON_TIME_TARGET.get(self.kind, 0.90) if target is None else float(target)
        if not self.served:
            return 0.0
        return max(t - self.rate, 0.0)


class DeficitCounters:
    """Per-device deficit counters, updated from the REALISED on-time outcome of each opportunity.

    On-time is the only thing observable online without ground truth (`arms_policy.py:276` says
    the same of the v1 counters, and it is the one thing about them v5 keeps). Correctness is not
    observable at run time, so it never enters an update here; it enters the objective through the
    committed accuracy table instead. That split is gap G14, kept deliberately and recorded.
    """

    def __init__(self, gain: float = DEFICIT_GAIN) -> None:
        self.gain = float(gain)
        self.devices: Dict[str, DeviceDeficit] = {}
        self.n_updates = 0

    def observe(self, device_id: str, on_time: bool, kind: str = "robot") -> None:
        d = self.devices.setdefault(device_id, DeviceDeficit(device_id, kind))
        d.served += 1
        d.on_time += 1 if on_time else 0
        self.n_updates += 1

    def shortfall(self, device_id: str) -> float:
        d = self.devices.get(device_id)
        return d.shortfall() if d else 0.0

    def weight(self, device_id: str) -> float:
        """`w_i = 1 + gain * shortfall_i`, so a device meeting its target weighs exactly 1.

        The floor at 1 is deliberate: a device AHEAD of its target is not worth LESS than a
        correct answer is worth, it is simply not worth more. Letting w fall below 1 would make
        the objective trade a correct answer for a fairness statistic, which D149 (1) forbids.
        """
        return 1.0 + self.gain * self.shortfall(device_id)

    def starving(self, device_id: str, threshold: float = 0.10) -> bool:
        """Reader 5's `starving` flag (D149 (3)): a shortfall past a declared threshold."""
        return self.shortfall(device_id) >= float(threshold)

    def as_dict(self) -> Dict[str, Any]:
        return {"gain": self.gain, "n_updates": self.n_updates,
                "target": ON_TIME_TARGET, "target_source": ON_TIME_TARGET_SOURCE,
                "steers_on": "observable on-time (D152 (1))",
                "objective_scores": "on-time cloud answers (D177 (1))",
                "mismatch": "gap G14 CLOSED by D177 (1): one currency; see module docstring",
                "devices": {k: {"served": v.served, "on_time": v.on_time,
                                "rate": round(v.rate, 6),
                                "shortfall": round(v.shortfall(), 6),
                                "weight": round(self.weight(k), 6)}
                            for k, v in sorted(self.devices.items())}}


# ---------------------------------------------------------------------------
# The device side of the objective (D155 (3))


def device_wait_s(*, kind: str = "robot", question_id: Optional[str] = None,
                  episode_frames: Optional[int] = None) -> float:
    """The MEASURED wait for this question's own device answer (D171 (3))."""
    return DEVLAT.wait_s(kind=kind, question_id=question_id, episode_frames=episode_frames)


def p_device_on_time(deadline_s: float, wait_s: Optional[float] = None, *,
                     kind: str = "robot", question_id: Optional[str] = None,
                     episode_frames: Optional[int] = None) -> float:
    """P(the DEVICE's own answer arrives within this question's deadline), D155 (3) on D171 (3).

    `wait_s` is the measured latency for THIS question unless a caller supplies one explicitly
    (the negative control does, and only the negative control should).
    """
    w = (device_wait_s(kind=kind, question_id=question_id, episode_frames=episode_frames)
         if wait_s is None else float(wait_s))
    return 1.0 if float(w) <= float(deadline_s) else 0.0


# ---------------------------------------------------------------------------
# D191 (1): THE COMPARISON, RULED BY THE USER. ONE comparison decides, and both of its sides are
# COUNTS of expected on-time cloud answers, each device weighted by its own per-device deficit
# weight (D185: w_d = 1 + 2.0 * shortfall_d / target_d):
#
#     deviate if and only if   (weighted gain - weighted harm)  >  w_d * MARGIN_CF
#     MARGIN_CF = 0.6582 ON-TIME ANSWERS                        (D177 (3), `attainment_margin`)
#
# THERE IS NO DIVISION BY THE NUMBER SERVED, and that is the part a reader has to get right,
# because the draft of `attainment_delta` divided by it. THE TARGET NORMALISATION ALREADY LIVES
# INSIDE w_d (`shortfall_d / target_d`, D185, D178 (2)), so dividing the gain by the window as
# well normalises TWICE. What that does is not conservatism: a per-decision attainment RATE moves
# by about 1 / served, roughly 8e-4 on a 1,200-instant window, against a bar of 0.65824 - three
# orders of magnitude down - so the left-hand side can never reach the bar and the gate NEVER
# OPENS. A gate that never opens is CLAUDE.md Rule 2's `unscorable`, it produces a believable
# null rather than a crash, and no byte-identity digest can see it. The division is therefore
# GONE from this function rather than guarded.
#
# THE exact-primary / margin-primary QUESTION IS SETTLED AND DISSOLVED by the same ruling, and
# the concern that raised it is recorded here as RESOLVED rather than deleted. The draft carried
# `LEX_READING_DEFAULT` with two readings and a comment that they "behave oppositely": under a
# margin on the PRIMARY key, per-decision attainment deltas would sit far below MARGIN_CF and the
# primary key would be INERT, which is the opposite of lexicographic. That concern was right
# about the arithmetic and wrong about the premise. D191 (1) rules that ONE comparison decides,
# and that any secondary key breaks EXACT ties only. A tie-break that fires only on exact
# equality cannot be widened by a margin, so there is no second reading to choose and NO SWITCH
# IS OFFERED: `LEX_READINGS` and `LEX_READING_DEFAULT` are deliberately absent, because a switch
# for a settled question is how a superseded reading comes back.
#
# ---------------------------------------------------------------------------
# THE CURRENCY FLIP IS IN THIS COMMIT, WITH `cf_planner.plan_state`, AND THE PAIRING IS THE POINT.
#
# D177 (1) replaces the CURRENCY of `option_value` and `device_only_value`: w * P(on time)
# instead of expected correctness. Converting THIS MODULE ALONE would make the arithmetic
# inconsistent at its own live consumer, and the numbers are these:
#
#   `cf_planner.plan_state` scored every candidate as
#        w * p_question * acc * (p_warm - p_cold)  -  harm
#   with `acc = table["cloud_D2"] = 0.250` computed INLINE (plan_state's `gain`), not through
#   `option_value`. Converting `option_value` converts the HARM and would leave that GAIN in
#   correctness units, and the subtraction would mix two currencies - the exact error D177 exists
#   to prevent. THE INLINE FACTOR IS THEREFORE GONE from `plan_state` in the same commit.
#
#   MEASURED, with one displaced on-time answer at w = 1, through the two live callers:
#     arms_v6state._harm_warm (acc_cloud 0.25, acc_device 0.071429)   0.178571 -> 1.000000, 5.6x
#     cf_protect_defer.harm_on_time (acc_cloud 1.0, acc_device 0.0)   1.000000 -> 1.000000, 1.0x
#   RUNG 4 DID NOT NEED THE FLIP to be in on-time units: it already gets them from its OWN
#   arguments, which is what `cf_protect_defer` says it does and is checked rather than believed.
#   Rungs 2 and 3 are the ones whose gain was unconverted.
#
# WHAT MOVES, STATED AS ARITHMETIC AND NOT AS A HOPE. In `plan_state` the gain and the margin are
# both multiplied by 1 / 0.250 = 4.0 (the gain loses `acc = 0.250`; the margin is divided by
# `A_D2_DEV = 0.250`), while a harm that was priced with the device fallback live is multiplied by
# 1 / (0.250 - 0.071429) = 5.6. A comparison with harm = 0 is therefore EXACTLY SCALE INVARIANT
# and cannot move; every decision that can move is one where the harm term is within a factor
# 5.6 / 4.0 = 1.4 of its side of the bar. For `HOLD_BACK`, whose value IS `harm_warm`, the bar
# moves from `harm_warm_old > 0.16456` to `harm_warm_old > 0.16456 / 1.4 = 0.11754`, so the band
# that changes is a harm_warm of 0.11754 to 0.16456 old units at w = 1.
#
# ON A DRY CELL THAT BAND IS EMPTY, AND THAT IS NOT "THE FLIP IS DECISION-NEUTRAL". The committed
# rung-2 dry counters (`d188_qcache_key_fix_proofs.json`, proof_b arm_stats_off) price harm_warm
# 2,297 times and make it non-zero 1,596 times, with milli_sum == max == 178: 1,595 of the 1,596
# non-zero values are below 5e-4, four orders of magnitude under the band, and the single outlier
# 0.178 clears the bar on both sides of the flip. The mechanism is alive, non-zero and varying,
# and the band is simply far away ON THIS WORKLOAD: CLAUDE.md Rule 2's UNEXERCISED IN MAGNITUDE.
# A live cell prices differently (D174 part B3), and no byte-identity digest from a dry cell may
# be read as evidence that the flip does not matter.
LEX_READING = ("settled by user ruling D191 (1): ONE comparison decides, in counts of on-time "
               "cloud answers; a secondary key breaks EXACT ties only")
LEX_READING_SUPERSEDED_CONCERN = (
    "the draft offered 'exact-primary' against 'margin-primary' and warned they behave "
    "oppositely, because a margin on a window-NORMALISED primary key would leave it inert. "
    "RESOLVED, not deleted: D191 (1) removes the window normalisation from the comparison (it "
    "lives inside w_d) and confines the secondary key to exact ties, so neither reading survives "
    "as a choice")
CURRENCY_FLIP_STATUS = (
    "CLOSED. D177 (1)'s conversion of option_value and device_only_value is IN, in the same "
    "commit as cf_planner.plan_state's inline `acc = 0.250` (removed) and cf_planner._margin's "
    "read of attainment_margin, so no decision subtracts on-time-unit harm from correctness-unit "
    "gain at any point in the history. The quality table is reporting only (D177 (2)); the value "
    "READER itself lives in v5/value_readers.py and in the arms that select one, which this "
    "commit does not touch, and the `covex-v6-fair-novalue` arm is where its removal is scored. "
    "Measured, not assumed: gain and margin x4.0, a device-fallback-priced harm x5.6, so the "
    "band that moves is a HOLD_BACK harm_warm of 0.11754 to 0.16456 in old units at w = 1, and "
    "that band is empty on a dry cell (UNEXERCISED IN MAGNITUDE, not decision-neutral).")

# THE a_D2_DEV FACTOR, NOT RETYPED FROM A COMMENT. It is a committed constant whose authoritative
# declaration is `v5/margin_cf_d169.py:22`, the script that COMPUTED MARGIN_CF: its line 92 is
# `error = A_D2_DEV * abs(p_hat - 1[on time])` and its line 117 sets
# `margin_cf = error_p90_overall`. So the committed 0.16456 is a_D2_DEV times a p90 of
# |P_hat - outcome|, and dividing it by a_D2_DEV returns that p90, which is a PROBABILITY and so
# is already in on-time units. That is the whole of D177 (3)'s arithmetic and it introduces no
# number (D154 (2)). It is not imported, because importing `margin_cf_d169` would pull
# `cost_model_gate_d162` and `trace` into every process that imports this module; instead
# `a_d2_dev_declarations()` PARSES every declaration of the name in the tree, so "one constant"
# stays checkable the way `cf_margin.margin_cf_declarations` makes MARGIN_CF checkable.
A_D2_DEV = 0.250
A_D2_DEV_SOURCE = ("v5/margin_cf_d169.py:22 (the script that computed MARGIN_CF; its line 92 is "
                   "`error = A_D2_DEV * abs(p_hat - on_time)` and its line 117 sets "
                   "`margin_cf = error_p90_overall`), restated in v5/cf_margin.py:62 and "
                   "declared identically in v5/cf_ontime_frozen.py and v5/cf_ontime_d162.py")


def a_d2_dev_declarations() -> Dict[str, Any]:
    """Every declaration of the name `A_D2_DEV` in the tree, PARSED, and whether they agree.

    The point is not style. Two modules holding the same literal is how "one constant" stops
    being true without anyone editing either number (the one-price-source ruling of 2026-11-21,
    which this file already applies to QUEUE_TOKEN_S). A regex would also report the comment and
    docstring mentions above as declarations, so this walks the AST.
    """
    import ast
    import subprocess
    found: Dict[str, Any] = {}
    how = "git grep"
    try:
        files = subprocess.run(["git", "grep", "-l", "A_D2_DEV", "--", "*.py"],
                               cwd=str(REPO), capture_output=True, text=True,
                               check=False).stdout.split()
    except Exception:                                                          # noqa: BLE001
        files = []
    if not files:
        # A `git archive` checkout has no .git, so git grep returns NOTHING and this audit would
        # report "0 declarations, they agree" - a vacuous pass, and exactly the shape CLAUDE.md
        # calls an impossible success. The clean-checkout proofs run on such a tree, so the
        # fallback walk is the path that actually gets exercised there.
        how = "filesystem walk (no git index; results/ and figures/ hold no policy and are skipped)"
        for sub in ("experiments", "simulator", "plots"):
            d = REPO / sub
            if not d.is_dir():
                continue
            for q in d.rglob("*.py"):
                try:
                    if "A_D2_DEV" in q.read_text():
                        files.append(str(q.relative_to(REPO)))
                except Exception:                                              # noqa: BLE001
                    continue
    for rel in files:
        p = REPO / rel
        try:
            tree = ast.parse(p.read_text())
        except Exception:                                                      # noqa: BLE001
            continue
        for node in ast.walk(tree):
            tgts = []
            if isinstance(node, ast.Assign):
                tgts = list(node.targets)
            elif isinstance(node, ast.AnnAssign):
                tgts = [node.target]
            for t in tgts:
                if isinstance(t, ast.Name) and t.id == "A_D2_DEV":
                    try:
                        found[rel] = float(ast.literal_eval(node.value))
                    except Exception:                                          # noqa: BLE001
                        found[rel] = None
    vals = sorted({v for v in found.values() if v is not None})
    return {"declarations": found, "n": len(found), "distinct_values": vals,
            "agree": len(vals) == 1, "found_how": how, "this_module": A_D2_DEV,
            "source": A_D2_DEV_SOURCE,
            "note": ("`agree` requires EXACTLY ONE distinct value, not at most one: zero "
                     "declarations found means the audit did not run, and reporting that as "
                     "agreement is an impossible success")}


def attainment_margin(margin_cf: float) -> float:
    """MARGIN_CF (D169 step 3, correctness units) expressed in D177's ON-TIME units.

    0.16456 / 0.250 = 0.65824, which D177 (3) states as 0.6582 and D178 (5) uses as the bar:
    "MARGIN_CF 0.6582 scaled by the deficit weight of the device the decision is about".

    THE ONE THING A CALLER MUST GET RIGHT IS WHAT IT IS COMPARED AGAINST. The number returned is
    a COUNT of on-time cloud answers (0.65824 of one answer), because that is what dividing out
    a_D2_DEV leaves: a p90 of |P_hat - 1[on time]|, which is a probability, and a probability of
    one answer is a count of answers. It is therefore commensurable with, and only with,
    quantities summed as `w * p` over requests, which is what D171 (1)'s
    `(value_cf - value_base) > w_d x MARGIN_CF` compares and what `harm_warm_from_queue_delay`
    returns WHEN ITS CALLER PASSES `acc_cloud=1.0, acc_device=0.0` - which is what
    `cf_protect_defer.harm_on_time` does, and is how rung 4 obtains these units today.

    IT IS NOT COMMENSURABLE WITH A RATE. Any quantity divided by a per-device window count (a
    target-attainment RATE, D165 (A)'s window-normalised primary key) is smaller than this by
    about the size of that window, so comparing one against this margin gives a test that never
    passes. That is not a conservative bar, it is an absent mechanism (CLAUDE.md Rule 2,
    `unscorable`), and no committed ruling supplies a margin in rate units. If a rate-unit
    comparison is ever wanted, the margin for it has to be measured, not divided out of this one.

    IT IS NOW COMMENSURABLE WITH `cf_planner.plan_state`'s GAIN, and it was not before this
    commit: the inline `acc = 0.250` is gone from that gain and `cf_planner._margin` returns the
    margin through THIS function, so both sides of every state comparison are counts of on-time
    answers. See CURRENCY_FLIP_STATUS.
    """
    return float(margin_cf) / A_D2_DEV


def served_in_window(counters: Any, device_id: str) -> int:
    """How many opportunities of this device the counters have seen: the window DENOMINATOR.

    WHAT THIS IS FOR, AND WHAT IT IS NOT FOR, because the difference is D191 (1). D122 (B) asks
    that a device's progress be read against "that device's target window so a sparse-task device
    (about 4 questions per run) is not outweighed by a dense one (about 1,200 instants)", and
    this returns that window. It belongs to the SHORTFALL inside the deficit weight
    (`shortfall_d / target_d`, D185), which is where D191 (1) puts the target normalisation. IT
    IS NOT A DIVISOR ON THE GATE: dividing the gain or the harm by it would normalise twice and
    make the comparison unscorable, which is the point of the D191 (1) note above.

    A device with nothing served yet counts as 1 rather than 0. That is the correct limit and not
    a guard against a division: until something is served, the device's measured attainment is
    entirely decided by the next answer.

    REGISTER, marked at the point of use (CLAUDE.md): this is an ACCESSOR over the committed
    counters and, with the division removed, NOTHING IN THE DECISION PATH READS IT. Its readers
    are this module's tests and the reporting path. It is landed because D122 (B)'s window is
    wanted beside every weighted number, and it is named here as having no production read so
    that no one later mistakes it for a live mechanism (the `desired_tier` failure).
    """
    d = getattr(counters, "devices", {}).get(device_id) if counters is not None else None
    return max(int(getattr(d, "served", 0) or 0), 1)


def attainment_delta(weight: float, p_on_time_cf: float, p_on_time_base: float) -> float:
    """The DEVIATION's left-hand side, one device's share of it: `w * (p_cf - p_base)`.

    A COUNT of expected on-time cloud answers, weighted by that device's deficit weight, and
    commensurable with `attainment_margin` and with a harm built as `w * (p_before - p_after)`
    (D191 (1), D177 (1), D178 (5), D171 (1)).

    NO `served` ARGUMENT, by ruling and not by oversight. The draft divided by the number served,
    which made this a RATE three orders of magnitude below the margin; the D191 (1) note above
    has the arithmetic and the consequence. The target normalisation is inside `weight`.
    """
    return float(weight) * (float(p_on_time_cf) - float(p_on_time_base))


def lex_better(cand: Tuple[float, float], incumbent: Tuple[float, float]) -> bool:
    """Is `cand` better than `incumbent`? Each is (on-time count, expected correctness).

    ONE comparison decides (D191 (1)): the on-time count. The second element breaks EXACT ties
    only, which is why it is compared after an exact `==` and why NO MARGIN AND NO READING SWITCH
    is accepted here. See `LEX_READING` and `LEX_READING_SUPERSEDED_CONCERN`.

    Correctness is still the OUTCOME measured offline (D177 (1)); it appears here only as a
    deterministic tie-break, so a run cannot depend on dictionary order when two candidates are
    worth exactly the same number of on-time answers.
    """
    a_c, v_c = cand
    a_i, v_i = incumbent
    if float(a_c) != float(a_i):
        return float(a_c) > float(a_i)
    return float(v_c) > float(v_i)


# ---------------------------------------------------------------------------
# Option values


def option_value(weight: float, p_cloud_on_time: float, acc_cloud: float = 1.0,
                 p_dev_on_time: float = 1.0, acc_dev: float = 0.0) -> float:
    """`w * P(cloud answer on time)`: the expected ON-TIME CLOUD ANSWERS this option delivers.

    D177 (1). The clamp on `p` stays, so a prediction outside [0, 1] cannot buy or lose value.

    THE LAST THREE ARGUMENTS ARE REPORTING ONLY AND ARE NOT READ (D177 (2)), and they are kept
    rather than deleted so that the currency and every caller's signature do not change in one
    commit. They are not a write-only mechanism masquerading as a live one: nothing anywhere
    treats this function's accuracy arguments as a decision input any more, the callers that pass
    them do so to keep reporting the table they came from, and the two unit tests
    `test_cf_objective_d177.py` assert that varying them cannot move the return value. The
    superseded reading was D155 (3)'s "correct answers from EITHER source": a value of
    `p * acc_cloud + (1 - p) * p_dev * acc_dev`, where the second term priced the device's own
    answer. Under D177 the device answer is the INCUMBENT and not a candidate, so it is worth no
    CLOUD answers and the term is gone; the device's delivery probability keeps its two live
    roles, in `p_device_on_time` for the recent-frames rule and in the base policy's feasibility.
    """
    p = max(min(float(p_cloud_on_time), 1.0), 0.0)
    return float(weight) * p


def device_only_value(weight: float, p_dev_on_time: float = 1.0, acc_dev: float = 0.0) -> float:
    """EXACTLY 0.0: a device answer delivers no on-time CLOUD answers (D177 (1)).

    THE LARGEST SINGLE SEMANTIC CHANGE IN THE FLIP, named where it happens. It was
    `w * p_dev * acc_dev`, which at the committed table is `w * 1.0 * 0.071429`, so the
    DEVICE_ANSWERS and LEAVE_TO_DEVICE candidates used to compete on value; now they are the
    reference option worth zero, which is what "the device always answers" (D19, D152 (2)) means
    in a currency of cloud answers. The arguments are kept and not read, for the reason given in
    `option_value`. On origin this reaches `plan_request` and `plan_sync` only, whose sole caller
    is the `v5-full` family.
    """
    return 0.0


# ---------------------------------------------------------------------------
# Harm to others: a difference of two simulated queues


@dataclass(frozen=True)
class Harm:
    total: float
    rows: Tuple[Dict[str, Any], ...]
    n_affected: int

    def as_dict(self) -> Dict[str, Any]:
        return {"total": round(self.total, 9), "n_affected": self.n_affected,
                "rows": [dict(r) for r in self.rows]}


def harm_to_others(before: "CC.QueuePlan", after: "CC.QueuePlan", *, candidate_req_id: str,
                   counters: Optional[DeficitCounters] = None,
                   acc_by_req: Optional[Dict[str, float]] = None,
                   deadline_by_req: Optional[Dict[str, float]] = None,
                   acc_device: float = 0.0,
                   acc_device_by_req: Optional[Dict[str, float]] = None) -> Harm:
    """The expected correct on-time answers OTHER devices lose because this option was taken.

    Positive numbers are losses. Every row is one other request whose predicted delivery
    probability moved, with its own device's weight and its own accuracy, so the harm is in the
    same units as the gain and is never a tuned penalty.

    UNDER D177 (1) EACH ROW IS `w_o * (p_before - p_after)`, a count of the on-time CLOUD answers
    that other device loses, which is the form D191 (1) states. It is computed through
    `option_value`, so the harm and the gain cannot drift apart.

    D171 (2)'s REPLACEMENT SEMANTICS IS NOW ARITHMETICALLY INERT HERE, and that is a consequence
    of the currency and not a reversal of the ruling. Each row used to be
    `w_o * (p_before - p_after) * (acc_cloud_o - acc_dev_o * p_dev_on_time_o)`, where the
    `acc_dev_o` term is what D171 (2) added: a displaced request does not lose its whole cloud
    answer, because its own device answers instead. In a currency of CLOUD answers that
    subtraction has nothing to price - the displaced device's own answer is not a cloud answer -
    so the whole accuracy factor is gone and with it the distinction the switch
    `cf_planner.HARM_REPLACEMENT_SEMANTICS` selects. The ruling survives where it is still
    expressible: the displaced device's answer standing is why its loss is a probability
    difference and not a whole answer (D175 (1), D178 (4)). The accuracy arguments and the
    measured `p_device_on_time` (D171 (3)) are still computed and still REPORTED per row, so a
    reader can see what was displaced; they no longer enter `value_lost`.
    """
    b = before.by_id()
    a = after.by_id()
    rows: List[Dict[str, Any]] = []
    total = 0.0
    for rid, rb in b.items():
        if rid == candidate_req_id:
            continue
        ra = a.get(rid)
        if ra is None:
            continue
        w = (counters.weight(rb.device_id) if counters else rb.weight)
        acc = (acc_by_req or {}).get(rid, rb.accuracy)
        dl = (deadline_by_req or {}).get(rid, rb.deadline_abs_s)
        a_dev = (acc_device_by_req or {}).get(rid, float(acc_device))
        p_dev = (p_device_on_time(max(dl - rb.start_s, 0.0), kind=rb.kind,
                                  question_id=rb.question_id,
                                  episode_frames=rb.episode_frames)
                 if dl != math.inf else 1.0)
        vb = option_value(w, rb.p_on_time, acc, p_dev, a_dev)
        va = option_value(w, ra.p_on_time, acc, p_dev, a_dev)
        if abs(vb - va) > 0.0:
            rows.append({"req_id": rid, "device_id": rb.device_id, "weight": round(w, 6),
                         "p_on_time_before": round(rb.p_on_time, 6),
                         "p_on_time_after": round(ra.p_on_time, 6),
                         "accuracy": acc, "accuracy_device": a_dev,
                         "p_device_on_time": p_dev,
                         "value_lost": round(vb - va, 9)})
            total += vb - va
    return Harm(total, tuple(rows), len(rows))


# ---------------------------------------------------------------------------
# harm_warm: what a BACKGROUND WARM costs the requests queued behind it
#
# Pre-registered in `research/prereg_harm_warm_d172.md` BEFORE any grid was rerun under it.

# The committed D162 model's queued-ahead coefficient, read from the gate file rather than
# retyped. It is `first_token.per_queue_token`, NOT `per_uncached_token` (0.00018243, 19 percent
# larger): only the queued-ahead one answers what work placed AHEAD of a request costs THAT
# request, which is what a background warm does.
# ONE PRICE SOURCE (user ruling, 2026-11-21): imported, not re-declared. Two modules holding the
# same literal is how "identical in the planner and in the coordinator" stops being true without
# anyone editing either number.
try:
    import d162_price as _DP                                                   # noqa: E402
    QUEUE_TOKEN_S = _DP.PER_QUEUE_S
    QUEUE_TOKEN_S_SOURCE = "live2/d162_price.py::PER_QUEUE_S (" + _DP.SOURCE + ")"
except Exception:                                                              # noqa: BLE001
    QUEUE_TOKEN_S = 0.0001535807289338535
    QUEUE_TOKEN_S_SOURCE = ("results/orchestration/live2/frozen_test/cost_model_gate_d162.json :: "
                            "model.first_token.per_queue_token (gate commit 68a2b47)")
HEALTHY_FIRST_TOKEN_BOUND_S = 2.781          # D160 (2); the cap, never silent


@dataclass
class WarmHarm:
    total: float
    n_affected: int
    delta_t_s: float
    capped: bool
    rows: Tuple[Dict[str, Any], ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        return {"total": round(self.total, 9), "n_affected": self.n_affected,
                "delta_t_s": round(self.delta_t_s, 9), "capped": self.capped,
                "rows": [dict(r) for r in self.rows]}


def harm_warm_from_queue_delay(uncached_tokens: int,
                               others: Sequence[Dict[str, Any]], *,
                               p_on_time: Any, acc_cloud: float, acc_device: float,
                               counters: Optional[DeficitCounters] = None) -> WarmHarm:
    """`harm_warm`: the expected correct on-time answers that a warm of `uncached_tokens` costs
    the requests already queued behind it, PREDICTED from the D162 model (D172 follow-up ruling).

    Each `others` row is a pending request as a dict with `req_id`, `device_id`, `engine_s` (its
    own predicted service time) and `slack_s` (deadline minus now). The warm adds
    `QUEUE_TOKEN_S * uncached_tokens` seconds to each one's first token, which is a reduction of
    its slack by the same amount.

    THE VALUATION IS `option_value`, the same function `harm_to_others` uses, so this term and
    the request-decision harm are in one currency: under D177 (1), `w * (p_before - p_after)` on-
    time cloud answers per displaced request. `acc_cloud` and `acc_device` are still accepted and
    no longer read (see `option_value`), which is why THIS CALLER'S numbers move the most of
    anything in the flip: `arms_v6state._harm_warm` passes the committed table (0.250 and
    0.071429), so each displaced answer was worth 0.178571 and is now worth 1.000000, a factor
    5.6, while `cf_protect_defer.harm_on_time` passes 1.0 and 0.0 and does not move at all.

    THE CAP IS COUNTED. A warm whose added delay would push a request's first token past the
    healthy-regime bound is outside the range the D162 model was fitted on, so the delay is capped
    there and `capped` is set. D160 (2) does not trust the model across the saturation transition,
    and a silently extrapolated harm would be a number from outside the fit wearing a fitted
    number's clothes.
    """
    u = max(int(uncached_tokens), 0)
    dt = QUEUE_TOKEN_S * u
    capped = False
    if dt > HEALTHY_FIRST_TOKEN_BOUND_S:
        dt = HEALTHY_FIRST_TOKEN_BOUND_S
        capped = True
    rows: List[Dict[str, Any]] = []
    total = 0.0
    for r in others:
        w = (counters.weight(str(r.get("device_id"))) if counters else float(r.get("weight", 1.0)))
        eng = float(r.get("engine_s", 0.0))
        slack = float(r.get("slack_s", 0.0))
        p_dev = float(r.get("p_device_on_time", 1.0))
        pb = float(p_on_time(eng, slack))
        pa = float(p_on_time(eng, slack - dt))
        if pb == pa:
            continue
        vb = option_value(w, pb, acc_cloud, p_dev, acc_device)
        va = option_value(w, pa, acc_cloud, p_dev, acc_device)
        if vb == va:
            continue
        rows.append({"req_id": r.get("req_id"), "device_id": r.get("device_id"),
                     "weight": round(w, 6), "p_on_time_before": round(pb, 6),
                     "p_on_time_after": round(pa, 6), "value_lost": round(vb - va, 9)})
        total += vb - va
    return WarmHarm(total, len(rows), dt, capped, tuple(rows))


# ---------------------------------------------------------------------------
# The two properties of the weighting that a report must not get wrong


def weight_is_within_device_invariant(p_values: Sequence[float], accs: Sequence[float],
                                      weights: Sequence[float]) -> Dict[str, Any]:
    """PROOF that `w_i` cannot change which option ONE device's question takes.

    `w_i` multiplies every candidate of device i identically, so the argmax over that device's own
    candidate set is independent of `w_i`. Reported because the opposite claim is the natural
    mistake: "the objective is deficit weighted" reads as if the weighting affects every decision,
    and inside one request's candidate set it provably affects none. CLAUDE.md Rule 2 calls this
    shape `cancelled by geometry`, and a mechanism that cancels must be claimed where it does not.

    UNDER D177 (1) the `accs` argument no longer enters the values, so the argmax is over
    `p_values` alone. The proof is about `w_i` and is unaffected; `accs` is kept so the call sites
    and the reported rows are unchanged, and the `values` rows show the on-time counts.
    """
    rows = []
    for w in weights:
        vals = [option_value(w, p, a, 1.0, 0.0) for p, a in zip(p_values, accs)]
        rows.append({"weight": w, "argmax_index": max(range(len(vals)), key=lambda i: vals[i]),
                     "values": [round(v, 9) for v in vals]})
    argmaxes = {r["argmax_index"] for r in rows}
    return {"claim": "w_i cannot change the argmax within one device's candidate set",
            "weights_tried": list(weights), "rows": rows,
            "argmax_constant_across_weights": len(argmaxes) == 1,
            "verdict": ("CONFIRMED: cancelled by geometry within a device; the weighting's "
                        "characteristic decision is CROSS-DEVICE"
                        if len(argmaxes) == 1 else
                        "UNEXPECTED: the weight moved a within-device argmax, which the algebra "
                        "forbids; the implementation has a bug")}


def main() -> int:
    c = DeficitCounters()
    for i in range(10):
        c.observe("robo000", on_time=True)
    for i in range(10):
        c.observe("robo001", on_time=(i < 5))
    print(json.dumps({"objective": OBJECTIVE_STATEMENT,
                      "device_answer_wait_s": DEVICE_ANSWER_WAIT_S,
                      "device_answer_label": DEVICE_ANSWER_LABEL,
                      "counters": c.as_dict()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
