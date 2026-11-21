"""v5 VALUE READERS (D149, D151, D152), the design module for `research/policy_spec_v5.md`.

A value reader is a pure function from a decision's real alternatives to the one that maximises
DEFICIT-WEIGHTED EXPECTED CORRECT ON-TIME ANSWERS (D151 (4)). There are four, one per kind of
within-type alternative D149 (2) names: which representation (or tier) answers a question, which
history to warm or keep, which same-type request to shed under overload, and whose backlog to sync
after an outage. D149 (3)'s episode continuity is the fifth and is a reader over dashcam frames.

WHAT THIS MODULE IS AND IS NOT.
 - It is the reader arithmetic and the two checks the decisions demand of it: the switch-reaches-a-
   decision diff against the rule it replaces (CLAUDE.md Step 2b) and D149 (4)'s value-inversion
   acceptance test (CLAUDE.md Step 4).
 - It is NOT an arm, NOT a policy run and NOT evidence about outcomes. Nothing here touches a GPU,
   a model server or the live2 coordinator. `main()` reads committed JSON and writes JSON.
 - The accuracy table is a COMMITTED INPUT FILE, read, never a constant in this module. That is the
   `lh_req_quality.json` convention (`arms_policy._LhReqFittedProfiles`): refilling the table is a
   data update that leaves the reader byte-identical.

THE ACCEPTANCE TEST NEEDS THE READER AT ADMISSION, which is a correctness note and not a caveat.
Wired behind `c3_value_reader` in `hybrid_arm`, the reader is consulted only in C3's old fallback
slot, reached only when the full history did not fit, so the only candidate ever offered is RECENT.
Measured consequence on the dry seed-4 cell (`study_policy_v2_gate.md`, value-reader section): the
committed, flattened and inverted tables ALL give decision digest `5d3469549fead8ac`, so D149 (4)'s
acceptance test does not discriminate and is classified UNEXERCISED under CLAUDE.md Rule 2. That is
a failure of the test, not a pass of the mechanism. v5 calls the reader at ADMISSION over the full
D151 (3) candidate set (D2, RECENT, device), which is also where D151 (3) puts the robot decision.
The same cell shows the reader's digest is IDENTICAL to simply turning C3 off, which is why v5's
base policy is `hybrid-F-lhreq-noc3` rather than hybrid-F: taking C3 off is the decision the value
rule arrives at, not an ablation chosen for convenience.

D6 COMPLIANCE. The reader is FITTED on the DEV split (28 questions) and LH-REQ robots draw only
from the EVAL split (69). Every number the reader consults is a DEV number. EVAL numbers appear in
this module in exactly one place, `consequence_illustration`, which is labelled as an illustration
and is not read by any reader.

THE PRECISION THE TABLE ACTUALLY HAS. DEV cloud RECENT is 3 of 28, Wilson [0.037, 0.272]. D149 asks
for accuracy fitted BY HISTORY-LENGTH BAND; three bands over 28 questions hold about nine each and
would be noise given a shape, so NO BAND TABLE IS FITTED HERE and none is invented. `band_gap()`
states the gap and what would close it (P19). See spec v5 section 7.9.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "experiments/lib"))
from _provenance import stamp                                              # noqa: E402

LH_REQ_QUALITY = REPO / "results/orchestration/live2/lh_req/lh_req_quality.json"
OUT_DIR = REPO / "results/orchestration/live2/v5"

DEVICE = "DEVICE"

# D151 (1): the counterfactual deviates from the base only beyond a margin FIXED IN ADVANCE and
# NEVER TUNED. It is declared here so that a change to it is a visible edit to a named constant and
# not a swept parameter. MARGIN_SEND guards the reader's own send-or-let-the-device-answer call;
# MARGIN_CF guards the counterfactual's deviation from base hybrid-F. Both are in units of the
# objective: expected correct on-time answers.
MARGIN_SEND = 0.0
MARGIN_CF = 0.05


@dataclass(frozen=True)
class Option:
    """One real alternative at a decision point.

    name        what the policy would do (a representation, a tier, an ordering position)
    p_on_time   probability the answer is DELIVERED by the deadline under D146 completion delivery
    accuracy    probability that answer is correct, read from the committed DEV table
    gpu_s       accelerator seconds the option charges, used only by the shedding reader's density
    """
    name: str
    p_on_time: float
    accuracy: float
    gpu_s: float = 0.0

    @property
    def expected_correct(self) -> float:
        return float(self.p_on_time) * float(self.accuracy)


@dataclass(frozen=True)
class Choice:
    chosen: str
    value: float
    runner_up: Optional[str]
    runner_up_value: float
    margin_applied: float
    reason: str

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# The committed table


def load_dev_table(path: Path = LH_REQ_QUALITY) -> Dict[str, Any]:
    """The DEV block of the committed LH-REQ quality table, with its Wilson intervals kept.

    RAISES if the file is absent. A silent fallback would let a reader price a representation from
    a different question population, which is the failure `_LhReqFittedProfiles` exists to remove.
    """
    if not path.exists():
        raise FileNotFoundError("committed LH-REQ quality table missing: %s" % path)
    d = json.loads(path.read_text())
    dev = d["per_split"]["DEV"]
    return {
        "_source": str(path.relative_to(REPO)),
        "_fit_split": d.get("_fit_split"),
        "_draw_split": d.get("_draw_split"),
        "cloud_D2": float(dev["cloud_D2"]["accuracy"]),
        "cloud_RECENT": float(dev["cloud_RECENT"]["accuracy"]),
        "device": float(dev["device_4B_RECENT"]["accuracy"]),
        "n": int(dev["cloud_D2"]["n"]),
        "ci95": {k: dev[k]["ci95_wilson"] for k in ("cloud_D2", "cloud_RECENT", "device_4B_RECENT")},
        "_device_entry_is_a_substitution": (
            "the device entry is 4B x RECENT (D87) standing in for device-on-D2; no device-on-D2 "
            "result exists on these questions"),
        "_dev_coincidence": (
            "cloud RECENT and the device both score 3 of 28, but share only 1 of 3 questions, so "
            "the equality is arithmetic and not agreement"),
    }


def band_gap(path: Path = LH_REQ_QUALITY) -> Dict[str, Any]:
    """D149 asks for accuracy fitted BY HISTORY-LENGTH BAND. State the gap; do not fill it."""
    d = json.loads(path.read_text())
    dev = d["per_split"]["DEV"]
    lo, hi = dev["cloud_RECENT"]["ci95_wilson"]
    return {
        "asked_for": "accuracy DEV-fitted by history-length band (D149 (2))",
        "fitted": False,
        "why_not": (
            "the DEV split holds 28 questions and the AGGREGATE Wilson interval for cloud RECENT "
            "is already [%.3f, %.3f], a width of %.3f. Three bands would hold about nine questions "
            "each, so each band estimate would be noise given a shape, and a band table fitted on "
            "nine questions would be read later as a measurement." % (lo, hi, hi - lo)),
        "what_would_make_bands_fittable": (
            "P19, the full S-EMBER device sweep on the Orin under vLLM: all questions, RICH and "
            "RECENT, accuracy and latency. With accuracy measured per question over the whole set, "
            "bands are fitted on hundreds rather than on nine, and the device side of the "
            "comparison stops being the D87 4B x RECENT substitution."),
        "until_then": (
            "the reader consults ONE DEV-aggregate accuracy per (representation, tier) and the spec "
            "records that history length enters v5 only through p_on_time, never through accuracy."),
    }


# ---------------------------------------------------------------------------
# Reader 1: which representation, or the device, answers this question (D149 (2), D152 (2))


def representation_reader(options: Sequence[Option], device: Option,
                          margin: float = MARGIN_SEND, weight: float = 1.0) -> Choice:
    """Send a representation only if deficit-weighted P(on time) x accuracy beats the device's own
    answer by `margin`; otherwise the device answers.

    D152 (2) says the RECENT-only shortcut is not used for long-horizon questions: full history if
    it can arrive in time, otherwise the device answers. That rule is NOT written here. It FALLS
    OUT of this comparison on the committed DEV table, where cloud RECENT (0.107143) equals the
    device entry (0.107143), so RECENT's value p x 0.107143 cannot exceed the device's 1.0 x
    0.107143 for any p <= 1 and can only tie at p = 1. Ties go to the device.

    The device is the incumbent, so it wins ties and wins on an equal margin. That is the
    conservative direction: a tie broken toward the cloud spends GPU seconds and crowds every other
    request's decode window (frozen_test 18.7.2) for no expected gain.
    """
    dev_value = weight * device.expected_correct
    ranked = sorted(options, key=lambda o: (-weight * o.expected_correct, o.name))
    if not ranked:
        return Choice(DEVICE, dev_value, None, float("nan"), margin, "no cloud option offered")
    best = ranked[0]
    best_value = weight * best.expected_correct
    runner = ranked[1].name if len(ranked) > 1 else DEVICE
    runner_value = weight * ranked[1].expected_correct if len(ranked) > 1 else dev_value
    if best_value > dev_value + margin:
        return Choice(best.name, best_value, runner, runner_value, margin,
                      "beats the device by more than the margin")
    return Choice(DEVICE, dev_value, best.name, best_value, margin,
                  "no cloud option beats the device by more than the margin")


def recent_shortcut_rule(options: Sequence[Option], device: Option,
                         weight: float = 1.0) -> Choice:
    """The rule the reader REPLACES: the C3 degradation in `hybrid/hybrid_arm.py`.

    C3 sends RECENT whenever a full-history recall is infeasible but a RECENT one is feasible,
    without consulting accuracy at all. Reproduced here only so that Step 2b can diff the two on
    the same decisions; it is not part of v5.
    """
    by_name = {o.name: o for o in options}
    full = by_name.get("D2")
    recent = by_name.get("RECENT")
    if full is not None and full.p_on_time >= 0.5:
        return Choice("D2", weight * full.expected_correct, "RECENT",
                      weight * recent.expected_correct if recent else float("nan"), 0.0,
                      "full history predicted feasible")
    if recent is not None and recent.p_on_time >= 0.5:
        return Choice("RECENT", weight * recent.expected_correct, DEVICE,
                      weight * device.expected_correct, 0.0,
                      "full history infeasible, RECENT feasible")
    return Choice(DEVICE, weight * device.expected_correct, None, float("nan"), 0.0,
                  "neither representation feasible")


# ---------------------------------------------------------------------------
# Reader 2: which histories to warm or keep (D149 (2), D150 STATE)


def warm_keep_reader(candidates: Sequence[Dict[str, Any]], slots: int) -> List[Dict[str, Any]]:
    """Rank histories for warming or keeping by deficit-weighted expected correct on-time answers
    gained, net of the harm the warm charges to everyone else (D151 (4)).

    Each candidate declares, over the horizon D151 (4) fixes for a warm or keep decision (the
    history's next likely question, capped about 60 to 120 s):

        weight        the device's deficit weight (D149 (1))
        p_question    probability a question arrives for this history inside the horizon
        accuracy      cloud accuracy on the representation that would be sent, DEV-fitted
        p_on_time_warm, p_on_time_cold   delivery probability with and without the warm
        harm          expected correct on-time answers LOST by others, from the displacement this
                      warm causes: evictions it forces and the crowd it adds at their decode
                      windows. Positive numbers are losses.

    gain = weight * p_question * accuracy * (p_on_time_warm - p_on_time_cold) - harm

    The subtraction is the whole point. frozen_test 19.4 shows warming everything reaches 65 of 65
    robot questions at the committed capacity and only 34 of 65 at 0.25x, so at a tight pool a warm
    that evicts a history whose question is due is negative-value, and a reader without `harm`
    would rank it the same at both capacities.
    """
    scored = []
    for c in candidates:
        gain = (float(c["weight"]) * float(c["p_question"]) * float(c["accuracy"])
                * (float(c["p_on_time_warm"]) - float(c["p_on_time_cold"]))) - float(c.get("harm", 0.0))
        scored.append(dict(c, gain=gain))
    scored.sort(key=lambda c: (-c["gain"], str(c.get("id", ""))))
    for i, c in enumerate(scored):
        c["admitted"] = bool(i < slots and c["gain"] > 0.0)
    return scored


# ---------------------------------------------------------------------------
# Reader 3: which same-type request to shed under overload (D149 (2))


def shed_reader(requests: Sequence[Dict[str, Any]], gpu_s_to_free: float) -> Dict[str, Any]:
    """Shed the lowest deficit-weighted value per GPU-second first, within ONE type.

    WITHIN ONE TYPE is load-bearing and comes from D149 (1): value is never a cross-type exchange
    rate, because per GPU-second it would shed robots first. Cross-type precedence is decided by
    the deficit counters, never here.
    """
    ranked = sorted(requests,
                    key=lambda r: ((float(r["weight"]) * float(r["p_on_time"]) * float(r["accuracy"]))
                                   / max(float(r["gpu_s"]), 1e-6), str(r.get("id", ""))))
    shed, freed = [], 0.0
    for r in ranked:
        if freed >= gpu_s_to_free:
            break
        shed.append(r.get("id"))
        freed += float(r["gpu_s"])
    types = sorted({str(r.get("type", "?")) for r in requests})
    return {"shed": shed, "gpu_s_freed": freed, "types_present": types,
            "single_type": len(types) == 1}


# ---------------------------------------------------------------------------
# Reader 4: whose backlog to sync after an outage (D149 (2), D150 SYNC)


def backlog_reader(devices: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Order reconnecting devices by deficit-weighted expected correct on-time answers recoverable
    per GPU-second of prefill, and order WITHIN a device oldest-first.

    Oldest-first within a device is not a value judgement, it is forced: D148's episode context and
    a robot history are both APPEND-ONLY KV, and a token's KV depends on everything before it, so a
    later frame cannot be prefilled before an earlier one.
    """
    ranked = []
    for d in devices:
        value = float(d["weight"]) * float(d["p_question"]) * float(d["accuracy"]) * float(d["p_on_time_after"])
        ranked.append(dict(d, value=value, density=value / max(float(d["prefill_gpu_s"]), 1e-6),
                           within_device_order="oldest_first_append_only"))
    ranked.sort(key=lambda d: (-d["density"], str(d.get("id", ""))))
    return ranked


# ---------------------------------------------------------------------------
# Reader 5: episode continuity (D149 (3), D148)


def episode_continuity_reader(frames: Sequence[Dict[str, Any]], admit: int) -> List[Dict[str, Any]]:
    """Prefer an appended frame of an already warm episode over a cold episode start, with the
    deficit counters, not the value, preventing new devices from starving.

    The preference is a COST fact, not a taste: an appended frame prefills one frame onto a warm
    context while a cold start prefills the episode, and dropping an episode mid-way discards both
    the warm context and the trajectory evidence it carries (D149 (3)).

    `starving` is set by the deficit counters upstream. A starving device is admitted ahead of
    continuity, which is what stops continuity from being a lock-in rule.
    """
    scored = []
    for f in frames:
        value = float(f["weight"]) * float(f["accuracy"])
        density = value / max(float(f["gpu_s"]), 1e-6)
        scored.append(dict(f, value=value, density=density))
    scored.sort(key=lambda f: (not bool(f.get("starving")), not bool(f.get("warm_episode")),
                               -f["density"], str(f.get("id", ""))))
    for i, f in enumerate(scored):
        f["admitted"] = bool(i < admit)
    return scored


# ---------------------------------------------------------------------------
# The two checks the decisions demand


def _grid(table: Dict[str, Any], p_full: Iterable[float], p_recent: Iterable[float],
          acc: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
    """A declared SYNTHETIC grid of delivery probabilities against the committed DEV accuracies.

    SYNTHETIC IS THE LABEL, not a hedge: no committed run reports a per-question P(on time), so the
    grid sweeps it rather than claiming it. The ACCURACIES are committed; only the probabilities are
    swept, and the point of the sweep is that the reader's answer is the same across all of them.
    """
    acc = acc or {"D2": table["cloud_D2"], "RECENT": table["cloud_RECENT"], DEVICE: table["device"]}
    rows = []
    for pf in p_full:
        for pr in p_recent:
            opts = [Option("D2", pf, acc["D2"], gpu_s=2.4),
                    Option("RECENT", pr, acc["RECENT"], gpu_s=0.3)]
            dev = Option(DEVICE, 1.0, acc[DEVICE])
            reader = representation_reader(opts, dev)
            rule = recent_shortcut_rule(opts, dev)
            rows.append({"p_on_time_full": pf, "p_on_time_recent": pr,
                         "reader": reader.chosen, "reader_value": round(reader.value, 6),
                         "c3_rule": rule.chosen, "differs": reader.chosen != rule.chosen})
    return rows


def step2b_switch_diff(table: Dict[str, Any]) -> Dict[str, Any]:
    """CLAUDE.md Step 2b, applied to the reader as a switch: run the reader and the rule it replaces
    on the SAME decisions and diff them. Identical logs would mean the switch reaches no decision
    and the comparison has not been run."""
    ps = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    rows = _grid(table, ps, ps)
    differing = [r for r in rows if r["differs"]]
    return {
        "unit": "one robot question at one (p_on_time_full, p_on_time_recent) point",
        "n_decisions": len(rows),
        "n_differing": len(differing),
        "first_differing": differing[0] if differing else None,
        "reader_choice_counts": {k: sum(1 for r in rows if r["reader"] == k)
                                 for k in ("D2", "RECENT", DEVICE)},
        "c3_choice_counts": {k: sum(1 for r in rows if r["c3_rule"] == k)
                             for k in ("D2", "RECENT", DEVICE)},
        "verdict": ("SWITCH REACHES A DECISION" if differing else
                    "ABSENT LINK: the reader and the rule it replaces are indistinguishable"),
        "d152_2_falls_out": {
            "claim": ("D152 (2)'s rule, that the RECENT-only shortcut is not used for long-horizon "
                      "questions, is NOT written into the reader and is not needed as a rule"),
            "arithmetic": ("cloud RECENT = %.6f and the device = %.6f on the committed DEV table, "
                           "so p x %.6f <= 1.0 x %.6f for every p <= 1, with equality only at p = 1, "
                           "and ties go to the device"
                           % (table["cloud_RECENT"], table["device"],
                              table["cloud_RECENT"], table["device"])),
            "recent_chosen_anywhere_on_the_grid": any(r["reader"] == "RECENT" for r in rows),
            "caveat": table["_dev_coincidence"],
        },
    }


def step4_value_inversion(table: Dict[str, Any]) -> Dict[str, Any]:
    """D149 (4), which is CLAUDE.md Step 4 in the decisions' own words: flattening or inverting the
    value table MUST change decisions and outcomes, or value is decorative.

    The motivating failure is recorded in D149 itself: in the frozen policy (hybrid-F, F6) a flat
    table and a 10,000x inverted table moved ZERO decisions, because every decision there was a
    timing decision. This check is run on the READER, and a reader that passes it here still has to
    pass it inside a live arm before any v5 result is read; see spec v5 section 7.8.
    """
    ps = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    base = _grid(table, ps, ps)
    flat = _grid(table, ps, ps, acc={"D2": 0.25, "RECENT": 0.25, DEVICE: 0.25})
    inv = _grid(table, ps, ps, acc={"D2": table["cloud_RECENT"],
                                    "RECENT": table["cloud_D2"],
                                    DEVICE: table["device"]})
    x10k = _grid(table, ps, ps, acc={"D2": table["cloud_D2"] / 10000.0,
                                     "RECENT": table["cloud_RECENT"],
                                     DEVICE: table["device"]})

    def _diff(a, b):
        d = [(x["p_on_time_full"], x["p_on_time_recent"], x["reader"], y["reader"])
             for x, y in zip(a, b) if x["reader"] != y["reader"]]
        return {"n_changed": len(d), "of": len(a), "first": d[0] if d else None}

    out = {"cells": len(base),
           "flat_table": _diff(base, flat),
           "inverted_representations": _diff(base, inv),
           "full_history_devalued_10000x": _diff(base, x10k)}
    changed = [v["n_changed"] for k, v in out.items() if k != "cells"]
    out["verdict"] = ("VALUE IS LOAD-BEARING in the reader: every perturbation moves decisions"
                      if all(c > 0 for c in changed) else
                      "DECORATIVE on at least one perturbation: " + json.dumps(out))
    out["scope"] = ("this is the reader in isolation. It does NOT show that value moves OUTCOMES in "
                    "a run, which is what D149 (4) finally asks for and what only a live or "
                    "trace-driven v5 arm can show.")
    out["measured_in_arm"] = {
        "cell": "dry, seed 4, 16 devices, 1200 s, 40:40:20, LH-REQ robots",
        "source": "reports/study_policy_v2_gate.md, value-reader section; "
                  "results/orchestration/live2/frozen_test/value_reader_proofs.json",
        "digests": {"hybrid-Fv-lhreq": "5d3469549fead8ac",
                    "hybrid-Fv-flat-lhreq": "5d3469549fead8ac",
                    "hybrid-Fv-invert-lhreq": "5d3469549fead8ac",
                    "hybrid-F-lhreq-noc3": "5d3469549fead8ac",
                    "hybrid-F-lhreq": "ec49e6d5a3b5454f"},
        "outcome": "the three tables are indistinguishable in-arm: UNEXERCISED, Rule 2",
        "why": ("the reader sits in C3's fallback slot, reached only when the full history did not "
                "fit, so the only candidate ever offered is RECENT and every table withholds it"),
        "remedy": ("consult the reader at ADMISSION over D2, RECENT and the device, which is where "
                   "D151 (3) puts the robot decision"),
        "base_policy_consequence": ("the reader's digest equals hybrid-F-lhreq-noc3's exactly, so "
                                    "v5's base is noc3 and not hybrid-F"),
    }
    return out


def consequence_illustration(path: Path = LH_REQ_QUALITY) -> Dict[str, Any]:
    """What the reader would have done to the 18 RECENT releases frozen_test 21.2 measured.

    LABELLED AN ILLUSTRATION AND NOT A RESULT, for two reasons that both cut the same way:
      1. The 18 are a SELECTED subset, the longest histories, and the only device figure available
         for them is the EVAL aggregate over all 69. D152 (2) names this exact selection effect as
         why the live 11 percent and D151 (3)'s 26 percent differ, so applying an aggregate to a
         selected subset is the same error in the other direction.
      2. The decisions would have been made under a 5 s deadline by an arm that did not have a
         reader, so this is a re-score of someone else's choices, not a counterfactual run.
    """
    d = json.loads(path.read_text())
    ev = d["per_split"]["EVAL"]
    n_recent = 18
    return {
        "source": "reports/study_frozen_test.md section 21.2, hybrid-F post-fix at 3 s",
        "on_time_cloud_answers": 47, "sent_as_D2": 29, "sent_as_RECENT": n_recent,
        "measured_correct_rate_RECENT": 0.111, "measured_correct_rate_D2": 0.621,
        "reader_would_send_RECENT": 0,
        "expected_correct_from_those_18_as_sent": round(n_recent * 0.111, 3),
        "if_the_device_had_answered_them_EVAL_aggregate": round(
            n_recent * float(ev["device_4B_RECENT"]["accuracy"]), 3),
        "_status": "ILLUSTRATION, NOT A RESULT",
        "_why": ("the 18 are the longest histories and the device figure is an EVAL aggregate over "
                 "all 69, so the second number is an aggregate applied to a selected subset; the "
                 "direction is suggestive and the magnitude is not usable"),
        "_what_would_settle_it": ("per-question device answers on those same question ids, which "
                                  "P19 produces and the D146 Orin replacement of the D87 A6000 "
                                  "proxy would make the right stack for"),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="v5 value readers: checks on the committed DEV table")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    table = load_dev_table()
    checks = {
        "_what": ("v5 value readers (D149, D151, D152): the committed DEV table, the Step 2b switch "
                  "diff against the C3 RECENT shortcut, D149 (4)'s value-inversion acceptance test, "
                  "and the band gap stated rather than filled. OFFLINE, CPU only, no GPU, no model "
                  "server, no live run."),
        "_not_a_result": ("nothing here is evidence about policy OUTCOMES. These are checks on the "
                          "reader arithmetic over a declared synthetic grid of delivery "
                          "probabilities against COMMITTED accuracies."),
        "dev_table": table,
        "band_gap": band_gap(),
        "step2b_switch_diff": step2b_switch_diff(table),
        "step4_value_inversion": step4_value_inversion(table),
        "consequence_illustration": consequence_illustration(),
        "margins": {"MARGIN_SEND": MARGIN_SEND, "MARGIN_CF": MARGIN_CF,
                    "_note": "D151 (1): fixed in advance, never tuned"},
    }
    checks["_provenance"] = stamp(script="value_readers.py", model="n/a (policy design, no model)",
                                  device="a6000", n=checks["step2b_switch_diff"]["n_decisions"],
                                  args=args)
    p = out_dir / "value_readers_checks.json"
    p.write_text(json.dumps(checks, indent=1) + "\n")

    demo = {
        "_what": ("worked examples of the other four readers on DECLARED SYNTHETIC inputs, so that "
                  "the spec's prose has an arithmetic a reader can check by hand. The inputs are "
                  "invented and labelled; only the accuracies come from the committed DEV table."),
        "_inputs_are_synthetic": True,
        "warm_keep": warm_keep_reader([
            dict(id="robo003", weight=1.0, p_question=0.9, accuracy=table["cloud_D2"],
                 p_on_time_warm=0.97, p_on_time_cold=0.05, harm=0.0),
            dict(id="robo011", weight=1.0, p_question=0.3, accuracy=table["cloud_D2"],
                 p_on_time_warm=0.97, p_on_time_cold=0.05, harm=0.0),
            dict(id="robo017", weight=2.0, p_question=0.3, accuracy=table["cloud_D2"],
                 p_on_time_warm=0.97, p_on_time_cold=0.05, harm=0.40),
        ], slots=2),
        "shed": shed_reader([
            dict(id="q1", type="robot", weight=1.0, p_on_time=0.9, accuracy=table["cloud_D2"], gpu_s=2.4),
            dict(id="q2", type="robot", weight=1.0, p_on_time=0.2, accuracy=table["cloud_D2"], gpu_s=2.4),
            dict(id="q3", type="robot", weight=3.0, p_on_time=0.5, accuracy=table["cloud_D2"], gpu_s=2.4),
        ], gpu_s_to_free=2.4),
        "backlog": backlog_reader([
            dict(id="robo003", weight=1.0, p_question=0.9, accuracy=table["cloud_D2"],
                 p_on_time_after=0.95, prefill_gpu_s=2.0),
            dict(id="robo011", weight=1.0, p_question=0.9, accuracy=table["cloud_D2"],
                 p_on_time_after=0.95, prefill_gpu_s=6.0),
        ]),
        "episode_continuity": episode_continuity_reader([
            dict(id="dash07_frame", weight=1.0, accuracy=0.090, gpu_s=0.05, warm_episode=True),
            dict(id="dash22_start", weight=1.0, accuracy=0.090, gpu_s=0.40, warm_episode=False),
            dict(id="dash31_start", weight=1.0, accuracy=0.090, gpu_s=0.40, warm_episode=False,
                 starving=True),
        ], admit=2),
    }
    demo["_provenance"] = stamp(script="value_readers.py", model="n/a (policy design, no model)",
                               device="a6000", n=4, args=args)
    q = out_dir / "value_readers_demo.json"
    q.write_text(json.dumps(demo, indent=1) + "\n")

    print("wrote %s" % p)
    print("wrote %s" % q)
    print("step2b: %s (%d of %d decisions differ)"
          % (checks["step2b_switch_diff"]["verdict"],
             checks["step2b_switch_diff"]["n_differing"],
             checks["step2b_switch_diff"]["n_decisions"]))
    print("step4 : %s" % checks["step4_value_inversion"]["verdict"].split(":")[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
