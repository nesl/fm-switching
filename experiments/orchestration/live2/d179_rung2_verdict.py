#!/usr/bin/env python3
"""D179 (6) RUNG-2 VERDICT: the three pre-registered checks, scored PER SEED.

WRITTEN BEFORE THE SHARES CELLS EXIST, deliberately. The pre-registration is the header of
`results/orchestration/live2/frozen_test/runs/V6SHARES_CELLS`; the three checks are:

  1. alert per-episode target attainment AT LEAST THE BASE'S
  2. at least 90 percent of the committed rung-2 robot on-time GAIN OVER BASE retained
  3. assistance within 2 s AT LEAST 90 percent

PER SEED, NEVER POOLED AS THE VERDICT. A pooled figure can hide a per-seed failure, which is
consistency check 3's "a real effect averaged into undetectability". The pooled figure IS computed
and is reported BESIDE the per-seed table, under a name that says it is pooled.

THE COMPARATORS, both committed and both read by cell path, never by a remembered number:
  base              hybrid-F-lhreq-noc3, equivalently covex-v6-base (d181_share_floors.json's
                    `source` field states the identity), seeds 4 to 7, tag _L3_epg_rq30
  committed rung 2  covex-v6-state-uo, seeds 4 to 7, the PLAIN arm, not -c5attr
Status of both checked in research/EXPERIMENTS.md (StudyD179-SHARES, IN PROGRESS; neither
comparator carries an INVALID mark) before this script was written.

------------------------------------------------------------------------------------------------
THE DEFINITIONS, PINNED. Getting these wrong is the likeliest failure, so each one states the
quantity, the denominator, the committed source, and what it is NOT.

ON TIME (the delivery rule). PRIMARY is the committed scorer's rule, `score._within`:

    t_delivered - t_opportunity <= L + 1e-9

with `t_delivered` first put through the two committed passes of `scorer/score.py:load`, both of
which are transcribed in `_committed_delivery` below because this script must run on a box that
holds no trace tree and so cannot call `score.load`:

  D144 (2) / D175 (1)  a REFUSED request's delivery is nulled. Refused = non-200 http_status, or
                       no status at all with neither prompt_tokens nor output_tokens
                       (`score.refused_request_ids`).
  D146                 DELIVERY == "completion": for `kind == "recall"` ONLY, t_delivered is
                       re-based onto the request's `t_done` plus the same per-row forward delay.
                       A monitor Yes/No stays at first token plus the forward hop.

THE TRANSCRIPTION IS PROVED, NOT ASSERTED. The positive control re-derives
`robot_pool_on_time`, `ss_pool_on_time` and the dashcam on-time sum from `outcomes.jsonl.gz` plus
`request.jsonl.gz` and requires EXACT equality with the cell's own committed `score.score.sweep[0]`
block. On the eight committed comparator cells it reproduces all 24 counts exactly. If it does
not reproduce them, THIS SCRIPT IS BROKEN AND THE CELL IS NOT, and the run stops rather than
reporting a comparison.

SECONDARY, reported beside every alert figure and never mixed into it: `cloud_payload.on_time`,
the coordinator's own online flag, which is the FIRST-TOKEN reading. It is kept because the D178
deficit feed reads exactly this field, so the online mechanism's view of attainment and the
offline score's view are both on the page. On covex-v6-state-uo seed 4 the two differ by 140
monitor instants (2,209 against 2,349), which is `dashcam_ontime_reconcile.json`'s bucket
`late_at_forward_only` exactly. The two readings are the same name for different quantities and
a verdict is reported under BOTH; a disagreement between the two verdicts is flagged.

CLOUD ON-TIME ONLY (D177). `device_on_time` is never added to any numerator. It is not reported
here at all for the three checks; the cell's own `robot_headline` and `assistive_value` blocks
carry the device side and are untouched.

QUERY TYPE: BY DEVICE-ID PREFIX (dash -> alert, robo -> recall, asst -> assistance), which is
`share_admission.type_of_device`. NOT by request kind: `arms_v6fair.py:129` maps kind monitor to
dashcam and everything else to robot, and on every committed cell an `asst00x` completion arrives
as kind "recall" with deadline_s 2.0, so a kind-based split merges assistance into recall and
double-counts it. Verified per cell: the (prefix, kind, deadline_s) cross-tab must be exactly
{(dash, monitor, 1.0), (robo, recall, 3.0), (asst, recall, 2.0)} or the cell is flagged.

CHECK 1, "alert per-episode target attainment".

  EPISODE KEY = (play_id, int(round((t_local - 3.0) / 0.5)) // 21). This is the recipe
  `d178_deficit_feed_proofs.json` -> f_replay_committed_live_cell -> independent._how uses, and it
  is chosen over the EP-G prompt-token law (`deficit_feed.py` preference 2) because it is readable
  from the OUTCOME row alone and therefore sees episodes the policy never served, which the token
  law cannot. 21 is `trace.EPG_CAP_FRAMES`; `trace.EPG_MIN_FRAMES = 3` is why position 0 and 1 are
  not decision instants.

  PER-EPISODE DENOMINATOR = 19, A DECLARED CONSTANT (D178 (1)): positions 2 to 20 inclusive of the
  21-frame episode. Verified on the committed cell: 714 episodes, instants per episode min 2 /
  median 19 / max 19, the short ones being a play that ended mid-episode. The constant's bias is
  MEASURED, not assumed: on covex-v6-state seed 5 the true per-episode denominators give an alert
  shortfall of 0.1427 and the flat 19 over the same episodes gives 0.1467, so the constant costs
  +0.0040. BOTH are reported; the flat 19 is primary because it is the pre-registered denominator.

  MEAN PER-EPISODE AND POOLED ARE BOTH REPORTED, and only the per-episode one answers the check.
  On covex-v6-state seed 5 the per-episode alert shortfall is 0.1427 and the pooled shortfall over
  all 11,769 instants is 0.0411, a factor of 3.5, because 486 of 714 episodes are below target
  while the type as a whole is only just below it.

  ATTAINMENT AND SHORTFALL ARE DIFFERENT NUMBERS and are reported separately, because the two are
  easy to quote for each other: attainment_e = on_time_e / 19, shortfall_e = max(0, 0.25 -
  attainment_e), and the mean of the clipped shortfall is NOT 0.25 minus the mean attainment.
  The alert target is 0.25 per episode (D178 (1), spec v6 sections 2 and 8; it is also the
  committed scorer's p_dash). CHECK 1 compares the MEAN PER-EPISODE ATTAINMENT of shares against
  the base's, which is what "at least the base's" says; the fraction of episodes AT OR ABOVE the
  0.25 target is reported beside it, because that is the other thing "target attainment" can mean
  and the two can disagree.

CHECK 2, "robot on-time gain over base retained".

    gain      = rung2_on_time_fraction - base_on_time_fraction
    retained  = (shares_on_time_fraction - base_on_time_fraction) / gain

  DENOMINATOR = the cell's own robot pool, `score.score.sweep[0].robot_pool_n`, which is every `robo00x`
  opportunity in the cell. It is NOT the feasible subset and NOT a distinct-question count; a
  D159 (C) re-ask is its own opportunity with its own 3.0 s deadline and counts again. The pool
  size is trace-determined, so it must be EQUAL across the three arms at a given seed; on the
  eight committed comparator cells it is (132, 127, 121, 105) for both arms, and an inequality is
  a STOP, not a rescaling.

  NEAR-ZERO OR NEGATIVE DENOMINATOR, and NO SEED IS EVER SILENTLY DROPPED. A ratio on a
  vanishing denominator is unbounded and means nothing, so the seed is reported with
  `gain_class` and with an absolute fallback beside the ratio:
    gain >= +0.01            NORMAL. retained is the ratio; check 2 is retained >= 0.90.
    |gain| < 0.01            NO_GAIN_TO_RETAIN. The ratio is reported as null, the check is
                             VACUOUS for that seed and said to be, and the fallback bound is
                             applied: shares must not fall more than 0.01 below the base.
    gain <= -0.01            NEGATIVE_GAIN, the rung-2 arm LOST to the base on that seed. The
                             ratio is computed but marked UNINTERPRETABLE, because its sign
                             inverts and a "retention" above 0.9 would then mean shares is worse.
                             The fallback bound is applied instead.
  On the committed comparators the gain is +0.63 / +0.69 / +0.55 / +0.61, so the guard does not
  fire there; it exists because a shares cell can change which seeds have gain.

CHECK 3, "assistance within 2 s".

  DEADLINE 2.0 s, which is both the type's deadline in every committed cell and the committed
  scorer's `L_ss`. For assistance "within 2 s" and "on time" are the same test.

  DENOMINATOR IS PER DEVICE, because D178 (1) sets the assistance unit to the DEVICE: "90 % of the
  device's questions within 2 s". So the PRIMARY verdict is: every `asst00x` device at or above
  0.90. The pooled fraction over all assistance opportunities is reported beside it, and so is the
  per-device minimum, because a pooled 0.93 can sit on top of a device at 0.80.

  OFFERED, NOT DELIVERED. The denominator is the count of assistance OPPORTUNITIES in the cell
  (`score.score.sweep[0].ss_pool_n`), which is the offered count: 357 on seed 4 against the 1,429 that
  `d181_share_floors.json` records over the four base cells. A denominator of completions would
  read 100 percent for a device whose questions are all being declined, which is the exact case
  these checks exist to catch, and a share-admission arm is the arm most able to produce it.

------------------------------------------------------------------------------------------------
ALSO COMPUTED PER SEED, so the cross-check does not depend on the H100's own reading:

  hold time p50 and p90 per type       from the `share_hold` decision rows joined to the request
                                       log's t_submit on opportunity_id. One row per DISTINCT held
                                       instant (coordinator.py:1498-1506), never one per period,
                                       so a duration needs the release event and cannot come from
                                       the hold rows alone. A held instant that was never
                                       submitted is RIGHT-CENSORED and is counted under
                                       `never_submitted`, never dropped and never treated as a
                                       zero-length hold.
  release_infeasible per type          arm_stats `release_infeasible_{alert,recall,assistance}`,
                                       with the in-cell denominator `submitted_*` beside it, both
                                       mirrored by coordinator._mirror_d179_stats.
  planner abandonment                  arm_stats.planner_time_limit: decisions, abandoned_to_base,
                                       fraction, by_kind, and the cell's own `flag`. Recomputed
                                       here from the counts rather than trusted, and FLAGGED above
                                       1 percent on any kind or overall.
  share admits and denies per type     arm_stats `share_admit_*`, `share_deny_*`,
                                       `share_hold_instants_*`, `share_hold_periods_*`,
                                       `share_reason_*`. The port rule is applied: an arm must make
                                       its characteristic decision at least once, so a shares cell
                                       with zero denies of every type is flagged as having made no
                                       share decision.
  W over W_max WITHOUT recall present  a SIGNATURE CHECK. `share_w_over_wmax_types_TIME` and
                                       `share_w_over_wmax_types` are type-composition dicts. In
                                       the dry cell recall was present in ALL 18,476 overruns with
                                       no exception (d179_dry_s4_report.json W_over_capacity),
                                       because the oversize exemption is the only thing that can
                                       push W past W_max. An overrun with no recall in it is NEW
                                       and is flagged LOUDLY: it would mean W can overrun without
                                       the exemption, which no existing proof covers.

  REGISTER NOTE ON W, and it is why no bar is set on these numbers here: live W is submit to FIRST
  TOKEN, dry W is submit to SETTLE, because `on_first` is wired only when a real backend exists
  (procsplit.py:430-433). The dry report's 13.43 percent of virtual time above W_max and its 3.56x
  high water are SETTLE-basis quantities and size nothing. A live cell's W is reported here as the
  live quantity it is and is NOT compared against the dry figures.

------------------------------------------------------------------------------------------------
USAGE

  python d179_rung2_verdict.py --runs <runs dir> --out <json> [--report <md>]
                               [--seeds 4,5,6,7] [--tag _L3_epg_rq30]
                               [--shares-arm covex-v6-state-shares]
                               [--base-arm hybrid-F-lhreq-noc3]
                               [--rung2-arm covex-v6-state-uo]
                               [--control-only]

`--control-only` runs the positive control and the comparator pinning and writes them, which is
what is possible before any shares cell exists. Read-only on every input.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

TYPES = ("alert", "recall", "assistance")
PREFIX_TO_TYPE = {"dash": "alert", "robo": "recall", "asst": "assistance"}
DEADLINE_S = {"alert": 1.0, "recall": 3.0, "assistance": 2.0}
EXPECTED_CROSSTAB = {("dash", "monitor", 1.0), ("robo", "recall", 3.0), ("asst", "recall", 2.0)}

ALERT_TARGET = 0.25
ALERT_INSTANTS_PER_EPISODE = 19
EPG_CAP_FRAMES = 21
EPG_T_LOCAL_ORIGIN_S = 3.0
EPG_T_LOCAL_STEP_S = 0.5

SWEEP_REQUIRED_KEYS = ("robot_pool_n", "robot_pool_on_time", "robot_pool_fraction",
                       "ss_pool_n", "ss_pool_on_time", "ss_pool_fraction", "ss_per_device",
                       "dashcam_per_device", "dashcam_all_meet")

ROBOT_ACCURACY_REGISTER = (
    "robot_headline.correct_answers_delivered_by_deadline is an ACCURACY, not an on-time rate: "
    "its own `metric` field says correct_answers_delivered_by_deadline, and its definition is the "
    "cloud's answer when delivered within the deadline, ELSE THE DEVICE'S if the device's also "
    "arrived in time, else a miss. It is NOT the quantity check 2 names, for two separate "
    "reasons, and substituting it changes the check twice over. First, an on-time wrong answer "
    "scores zero and a correct late answer scores zero, so it is not a deadline-attainment rate. "
    "Second, it ADMITS THE DEVICE SIDE, which D177 and D179 (6) exclude: the currency is on-time "
    "CLOUD answers only and device_on_time is reported beside, never added. The device floor is "
    "0.371212 on all three arms at seed 4, identical, and the measured consequence is large: on "
    "seed 4 the on-time retention is (0.454545 - 0.265152) / (0.893939 - 0.265152) = 0.3012 while "
    "the by_deadline retention is (0.545455 - 0.469697) / (0.613636 - 0.469697) = 0.5267, because "
    "the accuracy reading compresses the numerator by 2.5x and the denominator by 4.4x. The two "
    "are reported side by side and the ON-TIME one is the check.")

RETAIN_BAR = 0.90
ASSIST_BAR = 0.90
GAIN_EPS = 0.01
ABANDON_FLAG = 0.01
EPS = 1e-9


def _read_jsonl(path_noext: str) -> List[Dict[str, Any]]:
    for cand, opener in ((path_noext + ".gz", gzip.open), (path_noext, open)):
        if os.path.exists(cand):
            with opener(cand, "rt") as fh:
                return [json.loads(l) for l in fh if l.strip()]
    return []


def _type_of(device_id: Any) -> Optional[str]:
    return PREFIX_TO_TYPE.get(str(device_id or "")[:4])


def _pct(k: int, n: int) -> Optional[float]:
    return round(k / n, 6) if n else None


def _committed_delivery(outcomes: List[Dict[str, Any]],
                        reqs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """The committed scorer's two delivery passes, keyed by opportunity_id.

    Transcribed from scorer/score.py:484-579 rather than imported, because `score.load` needs the
    trace tree (trace_meta.json, device_answers.jsonl) and this script must run on a box that holds
    only the run directories. The transcription is what the positive control exists to prove.
    """
    out = {o["opportunity_id"]: dict(o) for o in outcomes}
    failed = set()
    for r in reqs:
        hs = r.get("http_status")
        if hs is not None:
            try:
                if int(hs) != 200:
                    failed.add(r.get("request_id"))
            except (TypeError, ValueError):
                failed.add(r.get("request_id"))
            continue
        if not r.get("prompt_tokens") and not r.get("output_tokens"):
            failed.add(r.get("request_id"))
    for o in out.values():
        cp = o.get("cloud_payload") or {}
        if cp.get("request_id") in failed:
            o["t_delivered"] = None
            o["cloud_payload"] = None
            o["d144_failed_request"] = True
    done = {r["opportunity_id"]: float(r["t_done"]) for r in reqs
            if r.get("opportunity_id") and r.get("t_done") is not None}
    for oid, o in out.items():
        if o.get("kind") != "recall" or o.get("t_delivered") is None:
            continue
        if o.get("t_cloud_done") is None or oid not in done:
            continue
        o["t_delivered_first_token"] = o["t_delivered"]
        o["t_delivered"] = done[oid] + (float(o["t_delivered"]) - float(o["t_cloud_done"]))
    return out


def _within(o: Dict[str, Any], L: float) -> bool:
    td = o.get("t_delivered")
    return td is not None and (float(td) - float(o["t_opportunity"])) <= L + EPS


def _flag_on_time(o: Dict[str, Any]) -> bool:
    return bool((o.get("cloud_payload") or {}).get("on_time"))


def _episode_key(o: Dict[str, Any]) -> Any:
    pos = int(round((float(o["t_local"]) - EPG_T_LOCAL_ORIGIN_S) / EPG_T_LOCAL_STEP_S))
    return (o.get("play_id"), pos // EPG_CAP_FRAMES)


def _episode_pos(o: Dict[str, Any]) -> int:
    pos = int(round((float(o["t_local"]) - EPG_T_LOCAL_ORIGIN_S) / EPG_T_LOCAL_STEP_S))
    return pos % EPG_CAP_FRAMES


def _alert_episode_block(mons: List[Dict[str, Any]], on_time) -> Dict[str, Any]:
    eps: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    for o in mons:
        eps[_episode_key(o)].append(o)
    sizes = sorted(len(v) for v in eps.values())
    positions = sorted({_episode_pos(o) for o in mons})
    att_flat, att_true, sf_flat, sf_true, at_target = [], [], [], [], 0
    for v in eps.values():
        k = sum(1 for o in v if on_time(o))
        a_flat = k / float(ALERT_INSTANTS_PER_EPISODE)
        a_true = k / float(len(v))
        att_flat.append(a_flat)
        att_true.append(a_true)
        sf_flat.append(max(0.0, ALERT_TARGET - a_flat))
        sf_true.append(max(0.0, ALERT_TARGET - a_true))
        if a_flat >= ALERT_TARGET - 1e-12:
            at_target += 1
    n_inst = len(mons)
    pooled_k = sum(1 for o in mons if on_time(o))
    return {
        "n_episodes": len(eps),
        "n_instants": n_inst,
        "instants_per_episode": {
            "min": sizes[0] if sizes else None,
            "median": statistics.median(sizes) if sizes else None,
            "max": sizes[-1] if sizes else None,
        },
        "episode_positions_seen": {"min": positions[0] if positions else None,
                                   "max": positions[-1] if positions else None},
        "per_episode_PRIMARY": {
            "denominator": ALERT_INSTANTS_PER_EPISODE,
            "denominator_source": "D178 (1) declared constant, positions 2 to 20 of 21",
            "mean_attainment": round(sum(att_flat) / len(att_flat), 6) if att_flat else None,
            "mean_shortfall_clipped": round(sum(sf_flat) / len(sf_flat), 6) if sf_flat else None,
            "episodes_at_or_above_target": at_target,
            "fraction_of_episodes_at_or_above_target": _pct(at_target, len(eps)),
        },
        "per_episode_true_denominator_BESIDE": {
            "mean_attainment": round(sum(att_true) / len(att_true), 6) if att_true else None,
            "mean_shortfall_clipped": round(sum(sf_true) / len(sf_true), 6) if sf_true else None,
        },
        "pooled_BESIDE": {
            "on_time": pooled_k,
            "n_instants": n_inst,
            "attainment": _pct(pooled_k, n_inst),
            "shortfall_clipped": (round(max(0.0, ALERT_TARGET - pooled_k / n_inst), 6)
                                  if n_inst else None),
            "_why_beside": ("pooling understates the alert deficit by about 3.5x on the committed "
                            "cell (0.0411 against 0.1427); only the per-episode figure answers "
                            "check 1"),
        },
    }


def _hold_block(decisions: List[Dict[str, Any]],
                reqs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Hold durations per type from the share_hold rows, with censoring reported.

    A hold row carries `key`, which is the opportunity id at the two DEADLINE release sites
    (coordinator.py:962, 1269) and "touch:<session>" / "build:<session>" at the two BACKGROUND
    sites (1107, 1182). Background holds therefore have no request-log join and are counted
    separately rather than being forced into a type's distribution.
    """
    t_submit: Dict[str, float] = {}
    for r in reqs:
        oid = r.get("opportunity_id")
        if oid and r.get("t_submit") is not None and oid not in t_submit:
            t_submit[oid] = float(r["t_submit"])
    holds = [d for d in decisions if d.get("kind") == "share_hold"]
    per: Dict[str, Dict[str, Any]] = {}
    durations: Dict[str, List[float]] = defaultdict(list)
    censored: Dict[str, int] = defaultdict(int)
    background = 0
    unkeyed = 0
    for d in holds:
        # The held instant travels in `opportunity_ids`, NOT in a `key` field: _log_decision takes
        # `key` as a keyword but passes it only to the prediction lookup and never into the
        # DecisionRecord (coordinator.py:1970-1991), so `rec["key"]` does not exist. Reading `key`
        # resolved 0 of 1,266 hold rows on the first shares cell and the per-type hold
        # distributions came out empty while every other number looked right, which is the
        # write-only-field shape from the other side: a field that is READ and never written.
        ids = d.get("opportunity_ids") or []
        key = (str(ids[0]) if ids else d.get("key"))
        if key is None:
            unkeyed += 1
            continue
        key = str(key)
        if key.startswith("touch:") or key.startswith("build:"):
            background += 1
            continue
        qt = _OPP_TYPE.get(key)
        if qt is None:
            unkeyed += 1
            continue
        if key in t_submit:
            durations[qt].append(float(t_submit[key]) - float(d.get("t", 0.0)))
        else:
            censored[qt] += 1
    for qt in TYPES:
        vals = sorted(durations.get(qt, []))
        per[qt] = {
            "n_held_instants_with_a_submit": len(vals),
            "never_submitted_RIGHT_CENSORED": censored.get(qt, 0),
            "hold_s_p50": round(statistics.median(vals), 6) if vals else None,
            "hold_s_p90": (round(vals[min(len(vals) - 1, int(0.90 * (len(vals) - 1) + 0.5))], 6)
                           if vals else None),
            "hold_s_min": round(vals[0], 6) if vals else None,
            "hold_s_max": round(vals[-1], 6) if vals else None,
            "negative_holds_FLAG": sum(1 for v in vals if v < 0.0),
        }
    return {
        "n_share_hold_rows": len(holds),
        "background_holds_no_request_join": background,
        "rows_whose_type_could_not_be_resolved": unkeyed,
        "per_type": per,
        "_censoring": ("a held instant with no request row was never submitted, so its hold is "
                       "right-censored at the end of the run; it is counted, never dropped and "
                       "never scored as a zero-length hold"),
    }


_OPP_TYPE: Dict[str, str] = {}


def _planner_block(arm_stats: Dict[str, Any]) -> Dict[str, Any]:
    ptl = dict(arm_stats.get("planner_time_limit") or {})
    dec = ptl.get("decisions")
    ab = ptl.get("abandoned_to_base")
    frac = (ab / dec) if (isinstance(dec, (int, float)) and dec and ab is not None) else None
    by_kind = {}
    over = []
    for k, v in (ptl.get("by_kind") or {}).items():
        d2, a2 = v.get("decisions"), v.get("abandoned_to_base")
        f2 = (a2 / d2) if (d2 and a2 is not None) else None
        by_kind[k] = {"decisions": d2, "abandoned_to_base": a2,
                      "fraction": (round(f2, 8) if f2 is not None else None)}
        if f2 is not None and f2 > ABANDON_FLAG:
            over.append(k)
    if frac is not None and frac > ABANDON_FLAG:
        over.append("OVERALL")
    return {
        "budget_ms": ptl.get("budget_ms"),
        "decisions": dec,
        "abandoned_to_base": ab,
        "fraction_recomputed": (round(frac, 8) if frac is not None else None),
        "fraction_as_recorded": ptl.get("fraction"),
        "by_kind": by_kind,
        "over_1_percent": sorted(set(over)),
        "flag_recomputed": bool(over),
        "flag_as_recorded": ptl.get("flag"),
        "_register": ("cf_instrument.over_budget is a WALL-CLOCK limit, so this rate is a property "
                      "of the host CPU as well as of the policy; a flash rate is a LOWER BOUND "
                      "for an H100 cell (D115 (1), about 2.2x) and must not be quoted for one"),
    }


def _share_block(arm_stats: Dict[str, Any]) -> Dict[str, Any]:
    g = arm_stats.get
    admits = {t: g("share_admit_" + t) for t in TYPES}
    denies = {t: g("share_deny_" + t) for t in TYPES}
    hold_i = {t: g("share_hold_instants_" + t) for t in TYPES}
    hold_p = {t: g("share_hold_periods_" + t) for t in TYPES}
    reasons = {k: v for k, v in arm_stats.items() if str(k).startswith("share_reason_")}
    any_deny = any(bool(v) for v in denies.values())
    present = any(v is not None for v in list(admits.values()) + list(denies.values()))
    comp_time = dict(arm_stats.get("share_w_over_wmax_types_TIME") or {})
    comp_gate = dict(arm_stats.get("share_w_over_wmax_types") or {})
    no_recall_time = {k: v for k, v in comp_time.items() if "recall" not in str(k)}
    no_recall_gate = {k: v for k, v in comp_gate.items() if "recall" not in str(k)}
    return {
        "share_counters_present": present,
        "admits": admits,
        "denies": denies,
        "hold_instants": hold_i,
        "hold_periods": hold_p,
        "reasons": dict(sorted(reasons.items())),
        "port_rule": {
            "_claim": ("an arm must make its characteristic decision at least once; a shares arm "
                       "whose gate never denies has made no share decision, whatever its proofs "
                       "say"),
            "any_deny": any_deny,
            "pass": bool(present and any_deny),
        },
        "w": {
            "high_water_tokens": g("share_w_high_water"),
            "zero_returns": g("share_w_zero_returns"),
            "tracked_at_end": g("share_w_tracked_at_end"),
            "over_wmax_periods_TIME": g("share_w_over_wmax_periods_TIME"),
            "samples_TIME": g("share_w_samples_TIME"),
            "over_wmax_per_gate_call": g("share_w_over_wmax_periods"),
            "samples_per_gate_call": g("share_w_samples_per_gate_call"),
            "composition_TIME": comp_time,
            "composition_per_gate_call": comp_gate,
            "_register": ("LIVE W is submit to FIRST TOKEN; the dry report's W is submit to "
                          "SETTLE and is the larger of the two. These numbers must not be "
                          "compared against the dry cell's 13.43 percent or its 3.56x"),
        },
        "SIGNATURE_CHECK_overrun_without_recall": {
            "_claim": ("in the dry cell recall was present in ALL 18,476 overruns with no "
                       "exception, because only the oversize exemption can push W past W_max; an "
                       "overrun with no recall in it is NEW and no existing proof covers it"),
            "time_basis_buckets_without_recall": no_recall_time,
            "time_basis_count_without_recall": sum(int(v) for v in no_recall_time.values()),
            "gate_call_basis_buckets_without_recall": no_recall_gate,
            "gate_call_basis_count_without_recall": sum(int(v) for v in no_recall_gate.values()),
            "FLAG": bool(sum(int(v) for v in no_recall_time.values())
                         or sum(int(v) for v in no_recall_gate.values())),
        },
    }


def _release_block(arm_stats: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for t in TYPES:
        skipped = arm_stats.get("release_infeasible_" + t)
        out[t] = {"release_infeasible": skipped}
    out["submitted_denominators_in_cell"] = {
        k: v for k, v in arm_stats.items() if str(k).startswith("submitted_")}
    out["_denominator_note"] = ("the submitted_* counters are mirrored into arm_stats so a skip "
                                "COUNT has an IN-CELL denominator; forming the rate from another "
                                "arm's denominator is a cross-arm substitution dressed as a rate")
    return out


def read_cell(run_dir: str) -> Dict[str, Any]:
    cell_path = os.path.join(run_dir, "cell.json")
    coord_path = os.path.join(run_dir, "coordinator_result.json")
    cell = json.load(open(cell_path)) if os.path.exists(cell_path) else {}
    coord = json.load(open(coord_path)) if os.path.exists(coord_path) else {}
    outcomes = _read_jsonl(os.path.join(run_dir, "outcomes.jsonl"))
    reqs = _read_jsonl(os.path.join(run_dir, "request.jsonl"))
    if not reqs:
        reqs = _read_jsonl(os.path.join(run_dir, "requests.jsonl"))
    decisions = _read_jsonl(os.path.join(run_dir, "decision.jsonl"))
    if not decisions:
        decisions = _read_jsonl(os.path.join(run_dir, "decisions.jsonl"))

    crosstab = sorted({(str(o.get("device_id"))[:4], str(o.get("kind")),
                        float(o.get("deadline_s"))) for o in outcomes})
    crosstab_ok = set(crosstab) == EXPECTED_CROSSTAB

    delivered = _committed_delivery(outcomes, reqs)
    _OPP_TYPE.clear()
    for oid, o in delivered.items():
        qt = _type_of(o.get("device_id"))
        if qt:
            _OPP_TYPE[oid] = qt
    by_type: Dict[str, List[Dict[str, Any]]] = {t: [] for t in TYPES}
    for o in delivered.values():
        qt = _type_of(o.get("device_id"))
        if qt:
            by_type[qt].append(o)

    recomputed: Dict[str, Any] = {}
    for t in TYPES:
        L = DEADLINE_S[t]
        rows = by_type[t]
        k_committed = sum(1 for o in rows if _within(o, L))
        k_flag = sum(1 for o in rows if _flag_on_time(o))
        perdev: Dict[str, Dict[str, Any]] = {}
        groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for o in rows:
            groups[str(o.get("device_id"))].append(o)
        for dev, os_ in sorted(groups.items()):
            kk = sum(1 for o in os_ if _within(o, L))
            perdev[dev] = {"n": len(os_), "on_time": kk, "fraction": _pct(kk, len(os_))}
        fr = [v["fraction"] for v in perdev.values() if v["fraction"] is not None]
        recomputed[t] = {
            "deadline_s": L,
            "n_opportunities_OFFERED": len(rows),
            "on_time_COMMITTED_RULE": k_committed,
            "fraction_COMMITTED_RULE": _pct(k_committed, len(rows)),
            "on_time_CLOUD_FLAG_FIRST_TOKEN": k_flag,
            "fraction_CLOUD_FLAG_FIRST_TOKEN": _pct(k_flag, len(rows)),
            "per_device": perdev,
            "per_device_min_fraction": (min(fr) if fr else None),
            "per_device_all_at_or_above_0p90": (all(v >= ASSIST_BAR - 1e-12 for v in fr)
                                                if fr else None),
        }

    mons = [o for o in delivered.values() if _type_of(o.get("device_id")) == "alert"]
    alert_eps = {
        "numerator_COMMITTED_RULE_PRIMARY": _alert_episode_block(
            mons, lambda o: _within(o, DEADLINE_S["alert"])),
        "numerator_CLOUD_FLAG_FIRST_TOKEN_BESIDE": _alert_episode_block(mons, _flag_on_time),
    }

    # The D179 counters live on the COORDINATOR (`counts`) and are MIRRORED onto the arm by
    # `_mirror_d179_stats`, which exists only from 19d8b416 onward, so a cell older than that
    # carries them in one place and a newer cell in both. Reading the union means neither a
    # mirrored nor an unmirrored cell reads as having no share mechanism at all.
    arm_stats = dict(coord.get("counts") or {})
    arm_stats.update(dict(coord.get("arm_stats") or {}))
    # THE PATH IS cell.json -> score -> score -> sweep[0]. It is GUARDED rather than trusted,
    # because reading it one level short returns {} and every pool count then reads None, which is
    # indistinguishable from "the base cells carry no on-time counts". That mis-read happened once
    # and concluded the comparator had no counts: a missing field wearing the look of an absent
    # measurement, which is the wrong conclusion in the wrong direction. So the keys the block MUST
    # carry are named and their absence is a loud flag, never a None.
    score = ((cell.get("score") or {}).get("score") or {})
    sweep = (score.get("sweep") or [{}])[0]
    missing = [k for k in SWEEP_REQUIRED_KEYS if k not in sweep]
    rh = score.get("robot_headline") or {}
    committed = {
        "_path": "cell.json -> score -> score -> sweep[0]",
        "_required_keys_missing_FLAG": missing,
        "_path_resolved": bool(sweep) and not missing,
        "_keys_that_do_not_exist": {
            "dashcam_verdict": ("NOT a key of this block. The verdict key is dashcam_all_meet; "
                                "asking for dashcam_verdict reads None, which is a missing field "
                                "wearing the look of a failed check"),
        },
        "dashcam_all_meet": sweep.get("dashcam_all_meet"),
        "dashcam_eligible": sweep.get("dashcam_eligible"),
        "dashcam_excluded": sweep.get("dashcam_excluded"),
        "robot_pool_meets": sweep.get("robot_pool_meets"),
        "robot_pool_eligible": sweep.get("robot_pool_eligible"),
        "robot_per_device": sweep.get("robot_per_device"),
        "robot_worst_device": sweep.get("robot_worst_device"),
        "ss_classified_by": sweep.get("ss_classified_by"),
        "capacity_met": sweep.get("capacity_met"),
        "L_dash": sweep.get("L_dash"), "p_dash": sweep.get("p_dash"),
        "L_rob": sweep.get("L_rob"), "p_rob": sweep.get("p_rob"),
        "robot_by_deadline_ACCURACY_BESIDE": {
            "metric": rh.get("metric"),
            "value": rh.get("correct_answers_delivered_by_deadline"),
            "n": rh.get("n_by_deadline"),
            "device_only_robot_accuracy_FLOOR": ((score.get("device_only") or {})
                                                 .get("robot_accuracy")),
            "_register": ROBOT_ACCURACY_REGISTER,
        },
        "robot_pool_n": sweep.get("robot_pool_n"),
        "robot_pool_on_time": sweep.get("robot_pool_on_time"),
        "robot_pool_fraction": sweep.get("robot_pool_fraction"),
        "ss_pool_n": sweep.get("ss_pool_n"),
        "ss_pool_on_time": sweep.get("ss_pool_on_time"),
        "ss_pool_fraction": sweep.get("ss_pool_fraction"),
        "ss_per_device": sweep.get("ss_per_device"),
        "dashcam_n_instants": (sum(v["n_instants"] for v in
                                   (sweep.get("dashcam_per_device") or {}).values()) or None),
        "dashcam_on_time": (sum(v["on_time"] for v in
                                (sweep.get("dashcam_per_device") or {}).values()) or None),
        "delivery_rule": score.get("delivery_rule"),
        "on_time_rule": score.get("on_time_rule"),
        "target_defaults": score.get("target_defaults"),
    }
    return {
        "run_dir": run_dir,
        "cell_name": os.path.basename(run_dir.rstrip("/")),
        "arm": coord.get("arm") or cell.get("arm"),
        "arm_version": coord.get("arm_version"),
        "seed": cell.get("seed"),
        "n_devices": cell.get("n_devices") or coord.get("n_devices"),
        "run_valid": cell.get("run_valid"),
        "digests_equal": cell.get("digests_equal"),
        "n_errors": cell.get("n_errors"),
        "crosstab_prefix_kind_deadline": [list(x) for x in crosstab],
        "crosstab_matches_expected": crosstab_ok,
        "committed_score_block": committed,
        "recomputed": recomputed,
        "alert_episodes": alert_eps,
        "share_admission": _share_block(arm_stats),
        "release_recheck": _release_block(arm_stats),
        "planner_time_limit": _planner_block(arm_stats),
        "hold_times": _hold_block(decisions, reqs),
        "budget": {"budget_gpu_s": coord.get("budget_gpu_s"),
                   "budget_spent_gpu_s": coord.get("budget_spent_gpu_s"),
                   "budget_refusal": arm_stats.get("budget_refusal")},
    }


def positive_control(cells: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Re-derive each cell's committed counts from its raw logs and demand EXACT equality.

    This is consistency check 7: it validates the SCORER against arms whose numbers were committed
    before it existed. A broken scorer passes every check applied to the treatment, because the
    treatment is fine, so the control is checked first and the comparison is not read until it is
    green. An impossible failure and an impossible success are equally diagnostic, so the three
    quantities are checked independently rather than one standing in for the others.
    """
    rows = []
    for c in cells:
        cm = c["committed_score_block"]
        rc = c["recomputed"]
        checks = [
            ("robot_pool_on_time", cm["robot_pool_on_time"], rc["recall"]["on_time_COMMITTED_RULE"]),
            ("robot_pool_n", cm["robot_pool_n"], rc["recall"]["n_opportunities_OFFERED"]),
            ("ss_pool_on_time", cm["ss_pool_on_time"],
             rc["assistance"]["on_time_COMMITTED_RULE"]),
            ("ss_pool_n", cm["ss_pool_n"], rc["assistance"]["n_opportunities_OFFERED"]),
            ("dashcam_on_time", cm["dashcam_on_time"], rc["alert"]["on_time_COMMITTED_RULE"]),
            ("dashcam_n_instants", cm["dashcam_n_instants"],
             rc["alert"]["n_opportunities_OFFERED"]),
        ]
        per = []
        for name, want, got in checks:
            per.append({"quantity": name, "committed": want, "recomputed": got,
                        "agree": (want is not None and want == got)})
        rows.append({
            "cell": c["cell_name"],
            "arm": c["arm"],
            "seed": c["seed"],
            "checks": per,
            "pass": all(p["agree"] for p in per) and bool(c["crosstab_matches_expected"]),
            "crosstab_matches_expected": c["crosstab_matches_expected"],
        })
    return {
        "_what": ("the scorer re-derives six committed counts per cell from outcomes.jsonl.gz plus "
                  "request.jsonl.gz and must match the cell's own score.sweep[0] block EXACTLY"),
        "tolerance": "EXACT, 0 counts",
        "cells": rows,
        "n_cells": len(rows),
        "n_pass": sum(1 for r in rows if r["pass"]),
        "verdict": "PASS" if rows and all(r["pass"] for r in rows) else "FAIL",
        "_if_it_fails": ("THIS SCORER IS BROKEN AND THE CELL IS NOT. Report the scorer failure, "
                         "not the comparison."),
    }


def _by_deadline_beside(base, rung2, shares) -> Dict[str, Any]:
    """The accuracy reading of check 2, computed so nobody has to reach for it, labelled so nobody
    can mistake it for the check. See ROBOT_ACCURACY_REGISTER for why it is a different quantity.
    """
    v = {k: c["committed_score_block"]["robot_by_deadline_ACCURACY_BESIDE"]["value"]
         for k, c in (("base", base), ("rung2_committed", rung2), ("shares", shares))}
    g = (round(v["rung2_committed"] - v["base"], 6)
         if None not in (v["rung2_committed"], v["base"]) else None)
    d = (round(v["shares"] - v["base"], 6) if None not in (v["shares"], v["base"]) else None)
    return {
        "_register": ROBOT_ACCURACY_REGISTER,
        "values": v,
        "device_only_accuracy_FLOOR": {
            k: c["committed_score_block"]["robot_by_deadline_ACCURACY_BESIDE"]
            ["device_only_robot_accuracy_FLOOR"]
            for k, c in (("base", base), ("rung2_committed", rung2), ("shares", shares))},
        "gain": g,
        "delta": d,
        "retained_fraction_ON_AN_ACCURACY": (round(d / g, 6) if (g and d is not None
                                                                 and abs(g) >= GAIN_EPS) else None),
        "IS_NOT_THE_PRE_REGISTERED_CHECK": True,
    }


def _gain_class(gain: Optional[float]) -> str:
    if gain is None:
        return "MISSING"
    if gain >= GAIN_EPS:
        return "NORMAL"
    if gain <= -GAIN_EPS:
        return "NEGATIVE_GAIN"
    return "NO_GAIN_TO_RETAIN"


def verdict_for_seed(seed: int, base: Optional[Dict[str, Any]],
                     rung2: Optional[Dict[str, Any]],
                     shares: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"seed": seed,
                           "cells": {"base": base and base["cell_name"],
                                     "rung2_committed": rung2 and rung2["cell_name"],
                                     "shares": shares and shares["cell_name"]}}
    if not (base and rung2 and shares):
        out["status"] = "INCOMPLETE: a required cell is absent, so no check is scored for this seed"
        out["missing"] = [k for k, v in (("base", base), ("rung2_committed", rung2),
                                         ("shares", shares)) if v is None]
        return out

    def alert_mean(c, rule):
        return c["alert_episodes"][rule]["per_episode_PRIMARY"]["mean_attainment"]

    def alert_atfrac(c, rule):
        return (c["alert_episodes"][rule]["per_episode_PRIMARY"]
                ["fraction_of_episodes_at_or_above_target"])

    c1 = {}
    for label, rule in (("COMMITTED_RULE_PRIMARY", "numerator_COMMITTED_RULE_PRIMARY"),
                        ("CLOUD_FLAG_FIRST_TOKEN_BESIDE",
                         "numerator_CLOUD_FLAG_FIRST_TOKEN_BESIDE")):
        b, s = alert_mean(base, rule), alert_mean(shares, rule)
        c1[label] = {
            "mean_per_episode_attainment": {"base": b, "rung2_committed": alert_mean(rung2, rule),
                                            "shares": s},
            "delta_shares_minus_base": (round(s - b, 6) if (b is not None and s is not None)
                                        else None),
            "pass": (bool(s is not None and b is not None and s >= b - 1e-12)),
            "fraction_of_episodes_at_or_above_0p25": {
                "base": alert_atfrac(base, rule), "rung2_committed": alert_atfrac(rung2, rule),
                "shares": alert_atfrac(shares, rule)},
            "pooled_attainment_BESIDE": {
                k: v["alert_episodes"][rule]["pooled_BESIDE"]["attainment"]
                for k, v in (("base", base), ("rung2_committed", rung2), ("shares", shares))},
        }
    c1["verdicts_agree_across_rules"] = (
        c1["COMMITTED_RULE_PRIMARY"]["pass"] == c1["CLOUD_FLAG_FIRST_TOKEN_BESIDE"]["pass"])
    c1["_check"] = "1. alert per-episode target attainment AT LEAST THE BASE'S"
    out["check_1_alert"] = c1

    pools = {k: v["committed_score_block"]["robot_pool_n"] if v["committed_score_block"]["robot_pool_n"]
             else v["recomputed"]["recall"]["n_opportunities_OFFERED"]
             for k, v in (("base", base), ("rung2_committed", rung2), ("shares", shares))}
    fr = {k: v["recomputed"]["recall"]["fraction_COMMITTED_RULE"]
          for k, v in (("base", base), ("rung2_committed", rung2), ("shares", shares))}
    cnt = {k: v["recomputed"]["recall"]["on_time_COMMITTED_RULE"]
           for k, v in (("base", base), ("rung2_committed", rung2), ("shares", shares))}
    same_pool = len(set(pools.values())) == 1
    gain = (round(fr["rung2_committed"] - fr["base"], 6)
            if None not in (fr["rung2_committed"], fr["base"]) else None)
    delta = (round(fr["shares"] - fr["base"], 6)
             if None not in (fr["shares"], fr["base"]) else None)
    gclass = _gain_class(gain)
    retained = (round(delta / gain, 6) if (gain and delta is not None and abs(gain) >= GAIN_EPS)
                else None)
    fallback = (delta is not None and gain is not None and delta >= gain - GAIN_EPS)
    if gclass == "NORMAL":
        c2_pass, basis = (retained is not None and retained >= RETAIN_BAR - 1e-12), "ratio"
    else:
        c2_pass, basis = fallback, "absolute fallback, the ratio being uninterpretable here"
    out["check_2_robot_retention"] = {
        "_check": ("2. at least 90 percent of the committed rung-2 robot on-time GAIN OVER BASE "
                   "retained"),
        "robot_pool_n": pools,
        "robot_pool_n_equal_across_arms": same_pool,
        "STOP_unequal_pool": (not same_pool),
        "on_time_counts": cnt,
        "on_time_fractions": fr,
        "gain_rung2_minus_base": gain,
        "delta_shares_minus_base": delta,
        "gain_class": gclass,
        "retained_fraction": retained,
        "retained_bar": RETAIN_BAR,
        "absolute_fallback_bound": {
            "rule": "shares on-time fraction must not fall more than 0.01 below the base's",
            "pass": fallback},
        "basis_used": basis,
        "by_deadline_ACCURACY_BESIDE_NOT_THE_CHECK": _by_deadline_beside(base, rung2, shares),
        "pass": bool(c2_pass and same_pool),
        "_no_seed_dropped": ("a seed whose denominator is near zero or negative is reported with "
                             "its gain_class and scored on the absolute fallback, never dropped "
                             "and never silently given a ratio"),
    }

    a = {k: v["recomputed"]["assistance"]
         for k, v in (("base", base), ("rung2_committed", rung2), ("shares", shares))}
    out["check_3_assistance"] = {
        "_check": "3. assistance within 2 s AT LEAST 90 percent",
        "deadline_s": DEADLINE_S["assistance"],
        "denominator": "the device's OFFERED assistance opportunities (D178 (1) unit = DEVICE)",
        "per_device_PRIMARY": {k: v["per_device"] for k, v in a.items()},
        "per_device_min_fraction": {k: v["per_device_min_fraction"] for k, v in a.items()},
        "all_devices_at_or_above_0p90": {k: v["per_device_all_at_or_above_0p90"]
                                         for k, v in a.items()},
        "pooled_BESIDE": {k: {"on_time": v["on_time_COMMITTED_RULE"],
                              "n": v["n_opportunities_OFFERED"],
                              "fraction": v["fraction_COMMITTED_RULE"]} for k, v in a.items()},
        "pass": bool(a["shares"]["per_device_all_at_or_above_0p90"]),
        "pass_on_pooled_BESIDE": bool(a["shares"]["fraction_COMMITTED_RULE"] is not None
                                      and a["shares"]["fraction_COMMITTED_RULE"]
                                      >= ASSIST_BAR - 1e-12),
    }
    out["all_three_pass"] = bool(c1["COMMITTED_RULE_PRIMARY"]["pass"]
                                 and out["check_2_robot_retention"]["pass"]
                                 and out["check_3_assistance"]["pass"])
    out["diagnostics_shares"] = {
        "share_admission": shares["share_admission"],
        "release_recheck": shares["release_recheck"],
        "planner_time_limit": shares["planner_time_limit"],
        "hold_times": shares["hold_times"],
        "budget": shares["budget"],
        "run_valid": shares["run_valid"],
        "digests_equal": shares["digests_equal"],
        "n_errors": shares["n_errors"],
    }
    return out


def _md(res: Dict[str, Any]) -> str:
    L: List[str] = []
    L.append("# D179 (6) rung-2 verdict: the three pre-registered checks, per seed")
    L.append("")
    L.append("Pre-registration: the header of "
             "`results/orchestration/live2/frozen_test/runs/V6SHARES_CELLS`.")
    L.append("")
    pc = res.get("positive_control") or {}
    L.append("## Positive control (read this first)")
    L.append("")
    L.append(f"Verdict **{pc.get('verdict')}**, {pc.get('n_pass')} of {pc.get('n_cells')} "
             "committed cells reproduced exactly.")
    L.append("")
    L.append("| cell | quantity | committed | recomputed | agree |")
    L.append("|---|---|---|---|---|")
    for c in pc.get("cells", []):
        for ch in c["checks"]:
            L.append(f"| {c['cell']} | {ch['quantity']} | {ch['committed']} | "
                     f"{ch['recomputed']} | {'yes' if ch['agree'] else '**NO**'} |")
    L.append("")
    if pc.get("verdict") != "PASS":
        L.append("**The scorer is broken, not the cells. No comparison is reported.**")
        return "\n".join(L) + "\n"
    L.append("## Per-seed verdict")
    L.append("")
    L.append("| seed | 1 alert | 2 retention | 3 assistance | all three |")
    L.append("|---|---|---|---|---|")
    for s in res.get("per_seed", []):
        if "check_1_alert" not in s:
            L.append(f"| {s['seed']} | - | - | - | {s.get('status')} |")
            continue
        L.append(f"| {s['seed']} | {s['check_1_alert']['COMMITTED_RULE_PRIMARY']['pass']} | "
                 f"{s['check_2_robot_retention']['pass']} | {s['check_3_assistance']['pass']} | "
                 f"{s['all_three_pass']} |")
    L.append("")
    L.append("| seed | alert att. base | alert att. shares | robot gain | retained | asst min dev |")
    L.append("|---|---|---|---|---|---|")
    for s in res.get("per_seed", []):
        if "check_1_alert" not in s:
            continue
        a = s["check_1_alert"]["COMMITTED_RULE_PRIMARY"]["mean_per_episode_attainment"]
        r = s["check_2_robot_retention"]
        m = s["check_3_assistance"]["per_device_min_fraction"]["shares"]
        L.append(f"| {s['seed']} | {a['base']} | {a['shares']} | {r['gain_rung2_minus_base']} "
                 f"({r['gain_class']}) | {r['retained_fraction']} | {m} |")
    L.append("")
    L.append("Pooled figures are in the JSON under `pooled_BESIDE_not_the_verdict`; they are "
             "reported beside the per-seed table and are never the verdict.")
    return "\n".join(L) + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    ap.add_argument("--seeds", default="4,5,6,7")
    ap.add_argument("--tag", default="_L3_epg_rq30")
    ap.add_argument("--suffix", default="_n16_s{seed}_1200s_h27_3t")
    ap.add_argument("--shares-arm", default="covex-v6-state-shares")
    ap.add_argument("--base-arm", default="hybrid-F-lhreq-noc3")
    ap.add_argument("--rung2-arm", default="covex-v6-state-uo")
    ap.add_argument("--control-only", action="store_true")
    ap.add_argument("--pins", help="json of pinned comparator shas to carry into the output")
    a = ap.parse_args(argv)

    seeds = [int(s) for s in a.seeds.split(",") if s.strip()]
    for s in seeds:
        if s not in (0, 4, 5, 6, 7):
            print(f"REFUSED: seed {s} is outside the permitted set 0, 4 to 7", file=sys.stderr)
            return 2

    def cell_dir(arm: str, seed: int) -> str:
        return os.path.join(a.runs, arm + a.suffix.format(seed=seed) + a.tag)

    loaded: Dict[str, Dict[int, Dict[str, Any]]] = {"base": {}, "rung2_committed": {},
                                                    "shares": {}}
    arm_of = {"base": a.base_arm, "rung2_committed": a.rung2_arm, "shares": a.shares_arm}
    absent: List[str] = []
    for role, arm in arm_of.items():
        for s in seeds:
            d = cell_dir(arm, s)
            if os.path.isdir(d) and os.path.exists(os.path.join(d, "outcomes.jsonl.gz")):
                loaded[role][s] = read_cell(d)
            else:
                absent.append(d)

    control_cells = ([loaded["rung2_committed"][s] for s in seeds if s in loaded["rung2_committed"]]
                     + [loaded["base"][s] for s in seeds if s in loaded["base"]])
    pc = positive_control(control_cells)

    res: Dict[str, Any] = {
        "_what": ("D179 (6): the three pre-registered rung-2 checks, scored PER SEED, with the "
                  "positive control, the pinned comparators and the definitions that were chosen "
                  "before any shares cell existed"),
        "_prereg": "results/orchestration/live2/frozen_test/runs/V6SHARES_CELLS (its header)",
        "arms": arm_of,
        "seeds": seeds,
        "tag": a.tag,
        "runs_dir": a.runs,
        "cells_absent": sorted(absent),
        "definitions": DEFINITIONS,
        "positive_control": pc,
    }
    if a.pins:
        res["pinned_comparators"] = json.load(open(a.pins))

    res["comparator_cells"] = {
        role: {str(s): {"cell": c["cell_name"], "arm": c["arm"],
                        "arm_version": c["arm_version"],
                        "run_valid": c["run_valid"], "digests_equal": c["digests_equal"],
                        "committed_score_block": c["committed_score_block"],
                        "recomputed": c["recomputed"],
                        "alert_episodes": c["alert_episodes"],
                        "planner_time_limit": c["planner_time_limit"]}
               for s, c in sorted(loaded[role].items())}
        for role in ("base", "rung2_committed")}

    if pc["verdict"] != "PASS":
        res["STOP"] = ("the positive control FAILED: this scorer is broken and the cells are not. "
                       "No comparison is reported.")
    elif not a.control_only:
        per_seed = [verdict_for_seed(s, loaded["base"].get(s), loaded["rung2_committed"].get(s),
                                    loaded["shares"].get(s)) for s in seeds]
        res["per_seed"] = per_seed
        scored = [p for p in per_seed if "check_1_alert" in p]
        res["per_seed_summary"] = {
            "n_seeds_scored": len(scored),
            "n_seeds_unscored": len(per_seed) - len(scored),
            "check_1_pass_seeds": [p["seed"] for p in scored
                                   if p["check_1_alert"]["COMMITTED_RULE_PRIMARY"]["pass"]],
            "check_2_pass_seeds": [p["seed"] for p in scored
                                   if p["check_2_robot_retention"]["pass"]],
            "check_3_pass_seeds": [p["seed"] for p in scored
                                   if p["check_3_assistance"]["pass"]],
            "all_three_pass_seeds": [p["seed"] for p in scored if p["all_three_pass"]],
            "_rule": ("the verdict is PER SEED. A seed that fails a check fails it; there is no "
                      "pooled rescue, because a pooled figure can hide a per-seed failure"),
        }
        pooled = {}
        for role in ("base", "rung2_committed", "shares"):
            cs = [loaded[role][s] for s in seeds if s in loaded[role]]
            if not cs:
                continue
            k = sum(c["recomputed"]["recall"]["on_time_COMMITTED_RULE"] for c in cs)
            n = sum(c["recomputed"]["recall"]["n_opportunities_OFFERED"] for c in cs)
            ka = sum(c["recomputed"]["assistance"]["on_time_COMMITTED_RULE"] for c in cs)
            na = sum(c["recomputed"]["assistance"]["n_opportunities_OFFERED"] for c in cs)
            pooled[role] = {"robot_on_time": k, "robot_n": n, "robot_fraction": _pct(k, n),
                            "assistance_on_time": ka, "assistance_n": na,
                            "assistance_fraction": _pct(ka, na),
                            "n_cells": len(cs)}
        res["pooled_BESIDE_not_the_verdict"] = {
            "_warning": ("reported BESIDE the per-seed table and never as the verdict; a pooled "
                         "figure can hide a per-seed failure (consistency check 3)"),
            "by_role": pooled}
    else:
        res["mode"] = ("control-only: the positive control and the comparator pinning, which is "
                       "what can be run before any shares cell exists")

    res["_provenance"] = {
        "git_commit": os.environ.get("D179_GIT_COMMIT", "unset"),
        "script": "d179_rung2_verdict.py",
        "model": "n/a (read-only scorer over committed run logs)",
        "device": "n/a (CPU)",
        "n": len(seeds),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as fh:
        json.dump(res, fh, indent=1, sort_keys=False)
        fh.write("\n")
    print(f"wrote {a.out}")
    print(f"positive control: {pc['verdict']} ({pc['n_pass']}/{pc['n_cells']} cells exact)")
    if a.report:
        with open(a.report, "w") as fh:
            fh.write(_md(res))
        print(f"wrote {a.report}")
    return 0 if pc["verdict"] == "PASS" else 1


DEFINITIONS = {
    "on_time_PRIMARY": {
        "rule": "t_delivered - t_opportunity <= deadline_s + 1e-9, score._within",
        "t_delivered_passes_applied": [
            "D144 (2) / D175 (1): a refused request's delivery is nulled (non-200 http_status, or "
            "no status with neither prompt_tokens nor output_tokens)",
            "D146 DELIVERY=completion: for kind == recall only, t_delivered is re-based onto the "
            "request's t_done plus the same per-row forward delay; a monitor stays at first token "
            "plus the forward hop",
        ],
        "source": "experiments/orchestration/live2/scorer/score.py:484-579, 687-689",
        "why_transcribed": ("score.load needs the trace tree, which this box does not hold; the "
                            "positive control proves the transcription against the cells' own "
                            "committed score blocks"),
    },
    "on_time_SECONDARY_beside": {
        "rule": "cloud_payload.on_time, the coordinator's own online flag",
        "register": "FIRST-TOKEN reading, not the committed completion-delivery reading",
        "why_kept": ("the D178 deficit feed reads exactly this field, so the online mechanism's "
                     "view and the offline score's view are both on the page; on "
                     "covex-v6-state-uo seed 4 they differ by 140 monitor instants, which is "
                     "dashcam_ontime_reconcile.json's late_at_forward_only bucket exactly"),
    },
    "currency": ("on-time CLOUD answers only (D177). device_on_time is never added to any "
                 "numerator here"),
    "query_type": {
        "rule": "device-id prefix: dash -> alert, robo -> recall, asst -> assistance",
        "source": "share_admission.type_of_device",
        "why_not_kind": ("arms_v6fair.py:129 merges assistance into recall by kind, and every "
                         "asst00x completion arrives as kind recall with deadline_s 2.0, so a "
                         "kind-based split double-counts recall"),
        "guard": ("the (prefix, kind, deadline_s) cross-tab must be exactly {(dash, monitor, "
                  "1.0), (robo, recall, 3.0), (asst, recall, 2.0)}"),
    },
    "alert_per_episode_attainment": {
        "episode_key": "(play_id, int(round((t_local - 3.0) / 0.5)) // 21)",
        "episode_key_source": ("d178_deficit_feed_proofs.json f_replay_committed_live_cell "
                               "independent._how; chosen over the EP-G prompt-token law because it "
                               "is readable from the outcome row alone and therefore sees "
                               "episodes the policy never served"),
        "epg_cap_frames": EPG_CAP_FRAMES,
        "epg_min_frames": 3,
        "denominator_PRIMARY": ALERT_INSTANTS_PER_EPISODE,
        "denominator_source": ("D178 (1) declared constant: positions 2 to 20 inclusive of the "
                               "21-frame episode, verified on a committed cell at 714 episodes, "
                               "instants per episode min 2 / median 19 / max 19"),
        "denominator_bias_measured": ("flat 19 gives 0.1467 against the true per-episode 0.1427 on "
                                      "covex-v6-state seed 5, so the constant costs +0.0040; both "
                                      "are reported"),
        "target": ALERT_TARGET,
        "target_source": "D178 (1), spec v6 sections 2 and 8; also the committed scorer's p_dash",
        "both_reported": ("MEAN PER-EPISODE and POOLED, and only the per-episode one answers "
                          "check 1; on covex-v6-state seed 5 the per-episode shortfall is 0.1427 "
                          "and the pooled shortfall is 0.0411, a factor of 3.5"),
        "attainment_vs_shortfall": ("attainment_e = on_time_e / 19, shortfall_e = max(0, 0.25 - "
                                    "attainment_e); the mean clipped shortfall is NOT 0.25 minus "
                                    "the mean attainment and the two are reported separately"),
        "check_1_quantity": ("the MEAN PER-EPISODE ATTAINMENT, compared against the base's. The "
                             "fraction of episodes at or above 0.25 is reported beside it because "
                             "that is the other reading of 'target attainment' and the two can "
                             "disagree"),
    },
    "robot_retention": {
        "gain": "rung2 on-time fraction minus base on-time fraction",
        "retained": "(shares minus base) / gain",
        "denominator": ("sweep[0].robot_pool_n, every robo00x opportunity in the cell; not the "
                        "feasible subset and not a distinct-question count, because a D159 (C) "
                        "re-ask is its own opportunity with its own 3.0 s deadline"),
        "pool_equality_guard": ("the pool is trace-determined and must be EQUAL across arms at a "
                                "seed; on the committed comparators it is 132 / 127 / 121 / 105 "
                                "for both arms, and an inequality is a STOP, not a rescaling"),
        "near_zero_or_negative_denominator": {
            "NORMAL": "gain >= +0.01: retained is the ratio, bar 0.90",
            "NO_GAIN_TO_RETAIN": ("|gain| < 0.01: the ratio is null and the check is VACUOUS for "
                                  "that seed and said to be; the absolute fallback applies"),
            "NEGATIVE_GAIN": ("gain <= -0.01: the ratio is reported but marked UNINTERPRETABLE "
                              "because its sign inverts; the absolute fallback applies"),
            "absolute_fallback": ("shares on-time fraction must not fall more than 0.01 below the "
                                  "base's"),
            "no_seed_dropped": "every seed is reported with its gain_class, never dropped",
        },
        "committed_gains": "base-to-rung2 gain is +0.629 / +0.693 / +0.545 / +0.610 on seeds 4 to 7",
        "NOT_by_deadline": ROBOT_ACCURACY_REGISTER,
    },
    "assistance_within_2s": {
        "deadline_s": 2.0,
        "unit_PRIMARY": ("the DEVICE (D178 (1)): every asst00x device at or above 0.90. The "
                         "pooled fraction and the per-device minimum are reported beside"),
        "denominator": ("OFFERED assistance opportunities (sweep[0].ss_pool_n = 357 on seed 4 "
                        "against d181_share_floors.json's 1,429 over the four base cells), not "
                        "completions: a completions denominator reads 100 percent for a device "
                        "whose questions are all being declined, the exact case these checks "
                        "exist to catch"),
        "same_test": "for assistance 'within 2 s' and 'on time' are the same test",
    },
    "W_register": ("live W is submit to FIRST TOKEN, dry W is submit to SETTLE (on_first is wired "
                   "only when a real backend exists, procsplit.py:430-433); the dry report's "
                   "13.43 percent of virtual time above W_max and its 3.56x high water are "
                   "SETTLE-basis and size nothing, so a live cell's W is never compared to them"),
    "overrun_signature_check": ("in the dry cell recall was present in ALL 18,476 overruns with no "
                                "exception, so an overrun with no recall in it is NEW and is "
                                "flagged loudly"),
    "seeds_permitted": "0, 4, 5, 6, 7 only; never 1 to 3 and never HOLDOUT",
}

if __name__ == "__main__":
    raise SystemExit(main())
