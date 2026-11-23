#!/usr/bin/env python3
"""CLAUDE.md Step 3 for the D178 (1) deficit feed: ONE TRACED UNIT PER TYPE, hand-checkable.

The unit of this mechanism is the unit of its target, and the three targets have three different
units (D178 (1)): an EPISODE for alert, a DEVICE for recall, a DEVICE for assistance. So there are
three traced units, not one, and each shows every input, the denominator and where it comes from,
the numerator and what counts into it, the clipped shortfall, and that unit's contribution to the
type weight.

READ-ONLY, from a COMMITTED LIVE CELL (`covex-v6-state_n16_s5_1200s_h27_3t_L3_epg_rq30`). No cell
is run here and no arm is constructed. A dry cell would be the wrong source for this trace: its
service model delivers almost every alert instant on time, so the alert unit would trace a
shortfall of zero and show nothing (the alert weight is UNEXERCISED in dry, which
`d178_deficit_feed_proofs.py` reports as such).

NOT A MEASUREMENT OF ANY ARM. The numbers are that one committed cell's own outcomes, shown so a
person can check the arithmetic of the feed by hand.
"""
from __future__ import annotations

import collections
import gzip
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
CELL = (REPO / "results/orchestration/live2/frozen_test/runs"
        / "covex-v6-state_n16_s5_1200s_h27_3t_L3_epg_rq30")
OUT = REPO / "results/orchestration/live2/frozen_test/d178_deficit_feed_trace.json"

for p in (str(HERE),):
    if p not in sys.path:
        sys.path.insert(0, p)
import deficit_feed as DF            # noqa: E402
import deficit_gain_d178 as GAIND    # noqa: E402
import share_capacity as SCAP        # noqa: E402

INSTANT_CADENCE_S = 0.5     # fleet/data_sources.NEXAR_INSTANT_CADENCE_S
INSTANT_T0_S = 3.0          # fleet/data_sources.NEXAR_GRID_T0_S


def main() -> int:
    outs = [json.loads(l) for l in gzip.open(CELL / "outcomes.jsonl.gz", "rt")]
    reqs = [json.loads(l) for l in gzip.open(CELL / "request.jsonl.gz", "rt")]
    ont = {r["opportunity_id"]: bool((r.get("cloud_payload") or {}).get("on_time")) for r in outs}
    pt = {r["opportunity_id"]: r.get("prompt_tokens") for r in reqs}
    served = set(pt)

    # ---- ALERT: one episode, all of its decision instants ------------------------------------
    byep: Dict[Any, List[Dict[str, Any]]] = collections.defaultdict(list)
    for r in outs:
        if not str(r["device_id"]).startswith("dash"):
            continue
        idx = round((float(r["t_local"]) - INSTANT_T0_S) / INSTANT_CADENCE_S)
        cyc, pos = divmod(idx, DF.EPG_CAP_FRAMES)
        byep[(r["device_id"], r["play_id"], cyc)].append(dict(
            instant_index=idx, episode_position=pos, opportunity_id=r["opportunity_id"],
            t_opportunity=r.get("t_opportunity"), deadline_s=r.get("deadline_s"),
            cloud_request_sent=r["opportunity_id"] in served,
            prompt_tokens=pt.get(r["opportunity_id"]),
            position_from_token_law=DF.position_from_prompt_tokens(pt.get(r["opportunity_id"])),
            cloud_on_time=ont.get(r["opportunity_id"], False),
            device_answer_exists=True))
    # a representative COMPLETE episode that is BELOW its target, which is the case the mechanism
    # exists to act on; the first such episode in trace order, not a chosen one
    pick = None
    for k in sorted(byep, key=lambda k: min(i["instant_index"] for i in byep[k])):
        items = sorted(byep[k], key=lambda i: i["instant_index"])
        n_ont = sum(1 for i in items if i["cloud_on_time"])
        if len(items) == DF.EPG_DECISION_INSTANTS and n_ont / DF.EPG_DECISION_INSTANTS < 0.25:
            pick = (k, items, n_ont)
            break
    k, items, n_ont = pick
    att = n_ont / DF.EPG_DECISION_INSTANTS
    alert = dict(
        unit="one ALERT EPISODE", device_id=k[0], play_id=k[1], episode_cycle=k[2],
        instants=items,
        denominator=dict(
            value=DF.EPG_DECISION_INSTANTS,
            how=("DECLARED CONSTANT: positions %d to %d of the 21-frame EP-G episode, because "
                 "D153's floor makes instants before the episode's third frame not decision "
                 "instants for any arm" % (DF.EPG_FIRST_POS, DF.EPG_LAST_POS)),
            source="deficit_feed.EPG_DECISION_INSTANTS, from fleet/trace.py EPG_CAP_FRAMES=21 "
                   "and EPG_MIN_FRAMES=3",
            observed_instants_in_this_episode=len(items),
            excluded_positions=[0, 1]),
        numerator=dict(value=n_ont, counts="cloud_on_time ONLY (D177, D178 (1))",
                       device_answers_on_time_not_counted=True),
        target=DF.TARGETS["alert"], attainment=round(att, 6),
        shortfall=round(max(DF.TARGETS["alert"] - att, 0.0), 6),
        weight_of_this_unit=round(
            GAIND.weight(max(DF.TARGETS["alert"] - att, 0.0), DF.TARGETS["alert"]), 6),
        weight_under_the_superseded_raw_form=round(
            1.0 + GAIND.GAIN * max(DF.TARGETS["alert"] - att, 0.0), 6),
        episode_key_derivation=dict(
            used_here="play_id and t_local, which only an offline reader has",
            used_by_the_feed=("the EP-G prompt-token law: position = (prompt_tokens - 42)/338 - 1,"
                              " and a position that does not rise is a new episode"),
            agreement_on_this_episode=[
                dict(instant_index=i["instant_index"], offline_position=i["episode_position"],
                     token_law_position=i["position_from_token_law"],
                     agree=(i["position_from_token_law"] is None
                            or i["position_from_token_law"] == i["episode_position"]))
                for i in items]),
        what_bound_it=("nothing in the feed BINDS: the feed produces a weight and the BINDING "
                       "happens in the consumer, share_admission.allowed, which splits the "
                       "flexible pool. The feed's own output for this unit is a shortfall."))

    # ---- RECALL and ASSISTANCE: one device each -----------------------------------------------
    def device_unit(prefix: str, qtype: str) -> Dict[str, Any]:
        bydev: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
        for r in outs:
            if not str(r["device_id"]).startswith(prefix):
                continue
            bydev[r["device_id"]].append(dict(
                opportunity_id=r["opportunity_id"], question_id=r.get("question_id"),
                t_opportunity=r.get("t_opportunity"), deadline_s=r.get("deadline_s"),
                cloud_request_sent=r["opportunity_id"] in served,
                cloud_on_time=ont.get(r["opportunity_id"], False)))
        # the device with the LARGEST shortfall, which is the case the mechanism exists to act on
        did = max(bydev, key=lambda d: -sum(1 for q in bydev[d] if q["cloud_on_time"])
                  / max(len(bydev[d]), 1))
        qs = sorted(bydev[did], key=lambda q: (q["t_opportunity"] or 0.0))
        n = len(qs)
        k_ont = sum(1 for q in qs if q["cloud_on_time"])
        att = k_ont / n if n else 1.0
        sf = max(DF.TARGETS[qtype] - att, 0.0)
        return dict(
            unit="one %s DEVICE" % qtype.upper(), device_id=did, questions=qs,
            denominator=dict(value=n, how=("OFFERED questions for this device, deduplicated by "
                                           "query id, NOT served ones: a question the policy "
                                           "declined never completes, and counting completions "
                                           "only would read a device whose questions are all "
                                           "declined as perfect"),
                             source="deficit_feed.observe_offered_question, fed from obs.recall "
                                    "with the roster's session_device map",
                             sent_to_cloud=sum(1 for q in qs if q["cloud_request_sent"])),
            numerator=dict(value=k_ont, counts="cloud_on_time ONLY (D177, D178 (1))"),
            target=DF.TARGETS[qtype], attainment=round(att, 6), shortfall=round(sf, 6),
            weight_of_this_unit=round(GAIND.weight(sf, DF.TARGETS[qtype]), 6),
            weight_under_the_superseded_raw_form=round(1.0 + GAIND.GAIN * sf, 6))

    rec = device_unit("robo", "recall")
    asst = device_unit("asst", "assistance")

    # ---- what the three units add up to, and what the consumer does with it -------------------
    feed = DF.DeficitFeed(gain=GAIND.GAIN)
    ev: List[Any] = []
    for r in outs:
        ev.append((float(r.get("t_opportunity") or 0.0), 0, r["device_id"], r["opportunity_id"]))
    for r in reqs:
        ev.append((float(r.get("t_done") or 0.0), 1, r["device_id"], r["opportunity_id"]))
    ev.sort(key=lambda e: (e[0], e[1]))
    # the episode key the OFFLINE reader can derive, passed in as `episode_id` so the replay uses
    # the same authority a live run does (the completion hook) rather than the token law
    epk = {r["opportunity_id"]: "%s|e%03d" % (r["play_id"],
                                              round((float(r["t_local"]) - INSTANT_T0_S)
                                                    / INSTANT_CADENCE_S) // DF.EPG_CAP_FRAMES)
           for r in outs if str(r["device_id"]).startswith("dash")}
    for _t, what, did, oid in ev:
        if what == 0:
            if str(did)[:4] == "dash":
                feed.observe_offered_instant(did, oid)
            else:
                feed.observe_offered_question(did, oid)
        else:
            feed.observe_completion(device_id=did,
                                    kind=("monitor" if str(did)[:4] == "dash" else "recall"),
                                    cloud_on_time=ont.get(oid, False), prompt_tokens=pt.get(oid),
                                    episode_id=epk.get(oid))
    w = feed.weights_by_type()
    tot = sum(w.values())
    consumer = {}
    for t, v in w.items():
        eq = SCAP.FLEXIBLE_TOKENS / 3.0
        wt = SCAP.FLEXIBLE_TOKENS * (v / tot)
        consumer[t] = dict(
            weight=round(v, 6), flexible_equal_split_tokens=round(eq, 1),
            flexible_weighted_tokens=round(wt, 1), delta_tokens=round(wt - eq, 1),
            floor_tokens=SCAP.FLOORS_TOKENS[t],
            share_equal=round(SCAP.FLOORS_TOKENS[t] + eq, 1),
            share_weighted=round(SCAP.FLOORS_TOKENS[t] + wt, 1),
            share_change_pct=round(100.0 * (wt - eq) / (SCAP.FLOORS_TOKENS[t] + eq), 2))

    out = dict(
        _what=("CLAUDE.md Step 3 for the D178 (1) deficit feed: one traced unit per type, each "
               "over its own denominator, plus what the consumer does with the three weights"),
        _source=str(CELL.relative_to(REPO)),
        _not_a_measurement=("read-only from one committed cell; no cell is run and no arm is "
                            "constructed here"),
        gain=GAIND.GAIN, gain_ruling=GAIND.GAIN_RULING,
        alert_unit=alert, recall_unit=rec, assistance_unit=asst,
        whole_cell=dict(per_device=feed.as_dict()["per_device"],
                        weights_by_type_max_over_devices=feed.as_dict()[
                            "weights_by_type_over_all_devices"],
                        type_shortfall_DIAGNOSTIC_ONLY=feed.as_dict()[
                            "type_shortfall_DIAGNOSTIC_ONLY"],
                        n_units=feed.as_dict()["n_units"],
                        counts=feed.as_dict()["counts"]),
        consumer_effect=dict(
            _what=("what share_admission.allowed does with these weights: the FLEXIBLE pool "
                   "(%0.1f of %0.1f uncached tokens) is split by weight; the FLOORS are not "
                   "weighted" % (SCAP.FLEXIBLE_TOKENS, SCAP.W_MAX_TOKENS)),
            by_type=consumer),
        reachable_weight_ranges=dict(
            _what=("a shortfall cannot exceed its own target, so the UNNORMALISED form's "
                   "reachable range differs by type and the declared 1 to 3 is reachable only by "
                   "a type whose target is 1"),
            by_type={t: [1.0, round(GAIND.weight(tg, tg), 3)] for t, tg in DF.TARGETS.items()},
            _corrected=("under the NORMALISED form the range is 1 to 3 for EVERY type; the row "
                        "below is what the SUPERSEDED raw form reached and is kept so the "
                        "correction's direction is visible in the trace too"),
            by_type_under_the_superseded_raw_form={
                t: [1.0, round(1.0 + GAIND.GAIN * tg, 3)] for t, tg in DF.TARGETS.items()}))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(dict(alert=dict(device=alert["device_id"], n=alert["denominator"]["value"],
                                     ont=alert["numerator"]["value"],
                                     sf=alert["shortfall"]),
                          recall=dict(device=rec["device_id"], n=rec["denominator"]["value"],
                                      ont=rec["numerator"]["value"], sf=rec["shortfall"]),
                          assistance=dict(device=asst["device_id"],
                                          n=asst["denominator"]["value"],
                                          ont=asst["numerator"]["value"], sf=asst["shortfall"]),
                          whole_cell=out["whole_cell"][
                              "weights_by_type_max_over_devices"]), indent=1))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
