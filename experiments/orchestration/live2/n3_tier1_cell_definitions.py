#!/usr/bin/env python3
"""N3 (D215 Tier 1): the three static-5G-link cell definitions, as data. NO CELLS ARE POSTED.

Tier 1 of D215 is median (all p50), poor (p10 bandwidth with high-percentile RTT) and mixed
fleet (a fixed seeded p10 / p50 / p90 assignment identical across arms). This script writes the
definitions, including the mixed-fleet assignment for seeds 4 and 5 so the fairness property can
be checked by eye, and the D215 / F12 instrumentation each cell must collect.

IT DOES NOT RUN OR POST A CELL. N1 found the per-device link has no injection point in any
production entry point (`link_by_device` is declared and defaulted in `fleet/emulator.py` and
passed by nothing), so a posted cell would be UNEXERCISED under CLAUDE.md Rule 2. That is
unchanged by the bandwidth ruling below: with or without correct values a Tier 1 cell would
differ from the main operating point in nothing.

BANDWIDTH, RULED 2026-11-23: Tier 1 uplink values come from CITED UPLINK SOURCES, namely the
committed StudyE1 sweep (uplink 5 / 12 / 13.6 / 25 / 88 Mbit/s, RTT 22 / 44 / 142 ms), each with
its source, and NEVER from the Irish 5G percentiles, which N2 established are DOWNLINK
(`DL_bitrate`) and whose `UL_bitrate` column is the ACK traffic of a download workload rather
than an uplink capacity.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments/orchestration/policy/audit"))
import _harness as H  # noqa: E402

ARMS = ("simplestream", "llf", "mooncake", "eco-llm", "confidence-cascade",
        "<final rung 3>", "<final rung 4>", "device-only")
SEEDS = (4, 5)

# THE TIER 1 BANDWIDTH AND RTT VALUES: the committed StudyE1 sweep, with the source each value
# carries in `reports/study_e1_nexar_lead.md` under "Network values cited". Where that block
# records NO source for a value, this says so rather than supplying one.
E1_UPLINK_MBIT_S = {
    5.0: "NO SOURCE RECORDED IN THE SWEEP: 5 Mbit/s is in the swept grid "
         "(study_e1_nexar_lead.md 'Sweep: uplink 5 / 12 / 13.6 / 25 / 88 Mbit/s') but the "
         "report's 'Network values cited' block gives no citation for it",
    12.0: "Khan et al. 2024, Bay Area 5G median (study_e1_nexar_lead.md 'Network values cited')",
    13.6: "best-performing US carrier's 5G median (Ookla H2 2025), close to the 12 Mbit/s Bay "
          "Area 5G median (Khan et al. 2024). CORRECTED LABEL, user ruling 2026-11-23 at "
          "`75d021d3`: these are T-Mobile's figures, the HIGHEST carrier median 5G upload "
          "(13.57 Mbit/s), NOT a US 5G median, so this is the OPTIMISTIC END of the range",
    25.0: "NO SOURCE RECORDED IN THE SWEEP, as for 5 Mbit/s",
    88.0: "Oslo (study_e1_nexar_lead.md 'Network values cited')",
}
E1_RTT_MS = {
    22.0: "the ICCCN paper, 22 ms median (study_e1_nexar_lead.md 'Network values cited'; the "
          "same line gives a 55 to 65 ms tail)",
    44.0: "LOWEST CARRIER LATENCY per Ookla H2 2025, paired with the 13.6 Mbit/s figure. "
          "CORRECTED LABEL as above: it is not a US median latency",
    142.0: "NO SOURCE RECORDED IN THE SWEEP: 142 ms is in the swept RTT grid but the 'Network "
           "values cited' block gives no citation for it",
}

# OBSERVED RTT, from this study's own extraction of the Irish 5G Download/Driving PINGAVG column
# (results/orchestration/live2/network/n2_irish5g_uplink_rtt_driving.json, n = 1,986 populated
# binned seconds of 24,446). Direction-agnostic: a ping RTT, unlike the bandwidth columns.
RTT_OBSERVED_MS = dict(p10=68.0, p50=80.0, p75=92.0, p90=120.0, p95=165.5, p99=351.35)

# N2, for the record and NOT for use in any cell.
DL_PCT_MBIT_S = dict(p10=0.8954, p50=9.5775, p90=102.898)      # DOWNLINK, RULED OUT
UL_COLUMN_PCT_MBIT_S = dict(p10=0.017, p50=0.093, p90=0.2337)  # ACK traffic, RULED OUT

MAIN_OPERATING_POINT = dict(
    uplink_mbps=13.6, rtt_ms=44.0,
    label="uniform 13.6 Mbit/s / 44 ms uplink: best-performing US carrier's 5G median (Ookla "
          "H2 2025), close to the 12 Mbit/s Bay Area 5G median (Khan et al. 2024)",
    correction="user ruling 2026-11-23, recorded at `75d021d3`. The earlier label 'Ookla H2 2025 "
               "US 5G median' was WRONG: these are T-Mobile's figures, the highest carrier "
               "median 5G upload and the lowest carrier latency, so the committed main operating "
               "point is the BEST-PERFORMING US CARRIER and sits at the optimistic end of the "
               "range rather than at its centre. The measurements are unaffected.",
    consequence="a 'median' condition is therefore NOT the main operating point, and the cells "
                "below are positioned against the StudyE1 sweep's own range rather than against "
                "13.6 Mbit/s as though it were typical",
    harness_source="D75 / StudyE4 / E9 / CTRL1c; applied by fleet/links.py:38-39")


def roster(seed: int, n_dev: int, ratio: str, run_s: float, mode: str):
    """The device roster, from the generator when its inputs are on this box, else derived.

    The derived path reproduces `trace.py::_split_fleet3` and the three id lists exactly. It
    exists because the assistive class needs the StudySS1 vizwiz manifest, which is an H100-side
    artefact and is not on flash: the ROSTER is a pure function of (n_devices, ratio) and does
    not depend on it, so the definition is still exact.
    """
    H.setup_paths()
    import fleet.trace as TR
    try:
        tr = TR.generate_trace(seed, int(n_dev), ratio, float(run_s), mode)
        return ([r["device_id"] for r in tr["records"] if r["kind"] == "device_register"],
                {r["device_id"]: r["type"] for r in tr["records"]
                 if r["kind"] == "device_register"}, "generator")
    except Exception as exc:
        n_dash, n_rob, n_ass = TR._split_fleet3(int(n_dev), ratio)
        ids, types = [], {}
        for pfx, n, ty in (("dash", n_dash, "dashcam"), ("robo", n_rob, "robot"),
                           ("asst", n_ass, "assistive")):
            for i in range(n):
                d = "%s%03d" % (pfx, i)
                ids.append(d)
                types[d] = ty
        return ids, types, "derived from trace.py::_split_fleet3 (%s: %s)" % (
            type(exc).__name__, str(exc).splitlines()[0])


CLASSES = ("slow", "median", "fast")


def mixed_assignment(seed: int, ids):
    """A FIXED seeded assignment of the three speed classes, IDENTICAL ACROSS ARMS.

    It is a function of (seed, sorted device roster) only: no arm, no run, no wall clock enters
    it, which is the fairness property D215 asks for. Thirds in sorted order after one seeded
    shuffle, so the class counts are as equal as 16 allows (6 / 5 / 5 at 16 devices).

    THE SEED IS A STRING ON PURPOSE. A first version seeded with the tuple
    `("tier1-mixed-5g", seed)`, and `random.seed` falls back to `hash()` for an arbitrary
    object, so a tuple containing a str is seeded from a PYTHONHASHSEED-randomised hash and the
    assignment CHANGED BETWEEN PROCESSES. That silently destroys the only property this function
    exists to provide, since two arms run in two processes. A str seed is hashed with sha512 by
    `random` itself and is stable across processes and machines.
    """
    ids = sorted(ids)
    order = list(ids)
    random.Random("tier1-mixed-5g|%d" % int(seed)).shuffle(order)
    out = {}
    for i, d in enumerate(order):
        out[d] = CLASSES[i % 3]
    return {d: out[d] for d in ids}


def reproducibility_proof(seed: int, ids) -> dict:
    """Recompute the assignment in fresh processes under three PYTHONHASHSEED values.

    Not decoration: the first version of `mixed_assignment` was seeded from a tuple and so from
    a randomised `hash()`, and this is the check that would have caught it. Two arms run in two
    processes, so an assignment that is stable only within one process is not identical across
    arms.
    """
    runs = {}
    for hs in ("0", "1", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=hs)
        out = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--emit-assignment",
             str(int(seed)), "--ids", ",".join(sorted(ids))],
            capture_output=True, text=True, env=env, check=True)
        runs[hs] = json.loads(out.stdout)
    vals = list(runs.values())
    return dict(pythonhashseeds=sorted(runs), identical=all(v == vals[0] for v in vals),
                assignment=vals[0])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--emit-assignment", type=int, default=None,
                    help="internal: print the assignment for this seed as JSON and exit")
    ap.add_argument("--ids", default=None, help="internal: comma-separated device ids")
    ap.add_argument("--devices", type=int, default=16)
    ap.add_argument("--ratio", default="50:50")
    ap.add_argument("--run-s", type=float, default=1200.0)
    ap.add_argument("--mode", default="A")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    if a.emit_assignment is not None:
        print(json.dumps(mixed_assignment(a.emit_assignment, a.ids.split(",")), sort_keys=True))
        return 0

    if not a.out:
        ap.error("--out is required")
    fleets = {}
    for s in SEEDS:
        ids, types, src = roster(s, a.devices, a.ratio, a.run_s, a.mode)
        asg = mixed_assignment(s, ids)
        fleets[str(s)] = dict(
            device_ids=sorted(ids), types=types, roster_source=src,
            mixed_class_by_device=asg,
            class_counts={c: sum(1 for v in asg.values() if v == c) for c in CLASSES},
            reproducibility_proof=reproducibility_proof(s, ids))

    instrumentation = [
        "applied_link_params_by_device (uplink_mbps, rtt_ms, downlink_mbps) LOGGED PER CELL, "
        "read back from the object the emulator actually holds, not from the CLI arguments",
        "per_frame_bytes and per_frame upload: t_offer, t_start, queue_s, t_arrive (the "
        "UplinkTransfer record), per device",
        "uplink queueing: n, busy_s, queue_p50, queue_p99, queue_max per device",
        "per_query upload: question bytes and upload time; AND the delta bytes a question "
        "carries, which does not exist yet (see blockers)",
        "history_batch bytes and upload time per batch",
        "standard F1 (correct-by-deadline per type and pooled), F2 (on-time vs correctness), "
        "F3 (latency CDFs), F13 (correct answers per GPU-second, GPU busy, tokens/s)",
        "the policy's BELIEVED link per device beside the applied one, because the two are "
        "wired separately (N1 read-site 6) and a robot's belief is currently hard-coded",
    ]

    def bw(v):
        return dict(uplink_mbps=v, source=E1_UPLINK_MBIT_S[v], register="CITED (StudyE1 sweep)")

    def rtt(v):
        return dict(rtt_ms=v, source=E1_RTT_MS[v], register="CITED (StudyE1 sweep)")

    cells = dict(
        median=dict(
            definition="every device at the sweep's cited MEDIAN uplink with the sweep's middle "
                       "RTT",
            bandwidth=bw(12.0),
            rtt=rtt(44.0),
            rtt_why="12 Mbit/s is the only value in the sweep cited AS a median that is not the "
                    "best-carrier figure, so it is the median cell's uplink; 13.6 is NOT used "
                    "here because the ruling's own correction says it is the optimistic end. RTT "
                    "44 ms is the sweep's middle value and keeps continuity with the main "
                    "operating point. THE ALTERNATIVE IS OPEN: the sweep's cited median RTT is "
                    "22 ms, which is 3.6x below this study's OBSERVED PINGAVG p50 of 80 ms, so a "
                    "'median' RTT could defensibly be 22 (cited), 44 (continuity) or 80 "
                    "(observed). 44 is the default here and the choice is flagged, not hidden.",
            rtt_observed_beside=dict(p50_ms=RTT_OBSERVED_MS["p50"],
                                     register="OBSERVED (Irish 5G PINGAVG, n 1,986)")),
        poor=dict(
            definition="every device at the sweep's slowest uplink with its tail RTT",
            bandwidth=bw(5.0),
            rtt=rtt(142.0),
            rtt_why="142 ms is the sweep's tail RTT and the poor cell is the tail condition. "
                    "D215 asks for p99 beside it: this study's OBSERVED PINGAVG p90 is 120 ms "
                    "and p99 is 351 ms, so the sweep's 142 ms sits between the observed p90 and "
                    "p99 and is the conservative-but-not-extreme choice.",
            rtt_observed_beside=dict(p90_ms=RTT_OBSERVED_MS["p90"], p99_ms=RTT_OBSERVED_MS["p99"],
                                     register="OBSERVED (Irish 5G PINGAVG, n 1,986)"),
            expected_scale="at 5 Mbit/s one 63,898 B dashcam JPEG serialises in 0.1022 s and "
                           "arrives 0.1733 s after capture on an idle uplink (RTT 142 ms); the "
                           "N1 probe measured the arithmetic at 0.9 Mbit/s, where the same frame "
                           "takes 0.568 s and 16 devices SATURATE the uplink to a 6.34 s median, "
                           "so saturation at 5 Mbit/s must be measured, not assumed"),
        mixed_fleet=dict(
            definition="a FIXED SEEDED slow / median / fast assignment, a function of (seed, "
                       "sorted device roster) only, so it is IDENTICAL ACROSS ARMS",
            bandwidth_by_class=dict(slow=bw(5.0), median=bw(12.0), fast=bw(88.0)),
            rtt_by_class=dict(slow=rtt(142.0), median=rtt(44.0), fast=rtt(22.0)),
            rtt_why="each class takes the sweep RTT that goes with its end of the range. PAIRING "
                    "A RATE WITH AN RTT IS CONSTRUCTED: the sweep is a full 5x3 grid and records "
                    "no joint distribution, and the Irish dataset gives no measured "
                    "bandwidth-RTT pairing for an uplink either.",
            sweep_values_not_used=dict(
                uplink_mbps=[13.6, 25.0],
                why="13.6 is the main operating point itself, so using it as a class would make "
                    "a third of the mixed fleet identical to the uniform condition; 25 Mbit/s "
                    "carries no source in the sweep's citation block and the fast class already "
                    "has the cited 88 Mbit/s"),
            rtt_observed_beside=dict(all_percentiles_ms=RTT_OBSERVED_MS,
                                     register="OBSERVED (Irish 5G PINGAVG, n 1,986)"),
            fleets=fleets),
    )

    res = dict(
        status="DEFINITIONS ONLY. NOT POSTED TO THE H100.",
        unchanged_by_the_bandwidth_ruling=(
            "TIER 1 STILL CANNOT BE POSTED. The ruling fixes the VALUES; N1's finding is about "
            "REACHABILITY, and with or without correct values a Tier 1 cell would differ from "
            "the main operating point in nothing. The 10 to 15 h of plumbing is the gate."),
        why_not_posted=("N1: the per-device link has NO injection point. `link_by_device` is "
                        "declared at fleet/emulator.py:245 and written at :291 and is passed by "
                        "no caller anywhere in experiments/, so every cell runs at the single "
                        "process-wide LinkSpec() default (13.6 Mbit/s, 44 ms). A posted cell "
                        "would differ from the main operating point in nothing, and a flat "
                        "result would be UNEXERCISED under CLAUDE.md Rule 2, not a finding."),
        positioning=("the cells are positioned against the StudyE1 sweep's own range, NOT "
                     "against 13.6 Mbit/s as though it were typical: per the 2026-11-23 "
                     "correction 13.6 / 44 is the BEST-PERFORMING US CARRIER, so the main "
                     "operating point is the optimistic end of the range and a 'median' "
                     "condition is a DIFFERENT, SLOWER cell than it."),
        arms=list(ARMS), seeds=list(SEEDS),
        seeds_note="seeds 4 and 5 only; never seeds 1 to 3 and never HOLDOUT",
        fleet=dict(n_devices=a.devices, ratio=a.ratio, run_s=a.run_s, mode=a.mode,
                   note="ratio and run_s carried over from the main operating point; confirm "
                        "against the D212 grid definition rather than assuming"),
        queue=dict(d212="all baseline cells are FILLER; policy cells always run first; the H100 "
                        "gates posted lists in order"),
        main_operating_point=MAIN_OPERATING_POINT,
        bandwidth_ruling=dict(
            ruled="2026-11-23, user. Tier 1 uplink values come from CITED UPLINK SOURCES, namely "
                  "the committed StudyE1 sweep (uplink 5 / 12 / 13.6 / 25 / 88 Mbit/s, RTT 22 / "
                  "44 / 142 ms), each with its source, and NEVER from the Irish 5G percentiles.",
            recorded_at="reports/study_e1_nexar_lead.md, correction block, commit `75d021d3`",
            ruled_out=dict(
                irish5g_downlink_percentiles_mbit_s=DL_PCT_MBIT_S,
                why_out="DOWNLINK (`DL_bitrate`, e31_network.py:84); using them would make every "
                        "poor cell far too generous as an uplink",
                irish5g_ul_column_mbit_s=UL_COLUMN_PCT_MBIT_S,
                why_ul_out="the ACK and control traffic of a download workload, not an uplink "
                           "capacity"),
            sweep_uplink_sources=E1_UPLINK_MBIT_S, sweep_rtt_sources=E1_RTT_MS,
            unsourced_in_the_sweep=dict(
                uplink_mbps=[5.0, 25.0], rtt_ms=[142.0],
                note="SMALL ESCALATION: the sweep's own 'Network values cited' block gives a "
                     "citation for 13.6, 12 and 88 Mbit/s and for 22 ms, and NONE for 5 and 25 "
                     "Mbit/s or for 142 ms. They are swept values, not cited ones. The poor cell "
                     "uses two of them, so they are marked rather than dressed as citations."),
            rtt_observed_vs_cited=dict(
                observed_ms=RTT_OBSERVED_MS,
                observed_register="OBSERVED, Irish 5G Download/Driving PINGAVG, 1,986 of 24,446 "
                                  "binned seconds populated (8.1 percent coverage)",
                cited_ms=sorted(E1_RTT_MS),
                disagreement="the sweep's cited MEDIAN RTT of 22 ms is 3.6x below the observed "
                             "p50 of 80 ms, which is over CLAUDE.md check 1's 2x bar. Explained "
                             "by setting rather than reconciled: the 22 ms is the ICCCN paper's "
                             "figure, the 80 ms is a driving trace in Ireland. Both registers "
                             "are carried and every cell says which it applies.")),
        cells=cells,
        instrumentation_D215_F12=instrumentation,
        blockers=[
            dict(id="B1", what="per-device link emulation has no injection point",
                 detail="no CLI flag, no caller of link_by_device, and fleet/trace.py emits "
                        "device_register with uplink_mbps=None, rtt_ms=None (:496, :591, :639), "
                        "which the emulator overwrites from its own LinkSpec at :476",
                 blocks="all three cells"),
            dict(id="B2", what="the committed 5G percentiles are DOWNLINK",
                 detail="RULED AND CLOSED 2026-11-23 (`75d021d3`): Tier 1 uplinks come from the "
                        "cited StudyE1 sweep, never from the Irish 5G percentiles. Kept as a row "
                        "so a reader meeting a downlink figure in an older note knows it was "
                        "ruled out rather than overlooked.",
                 blocks="NOTHING ANY MORE"),
            dict(id="B3", what="a question carries no delta",
                 detail="the only query-side upload is QUESTION_TEXT_B = 1200 B of text "
                        "(emulator.py:73, :417); D150 SYNC (2) 'a question carries any frames "
                        "the cloud lacks' is not implemented, so 'query delta upload time' is "
                        "ABSENT as a quantity",
                 blocks="the per-query delta bytes and delta upload time instrumentation"),
            dict(id="B4", what="a robot's believed link is hard-coded",
                 detail="cstate.py:628 builds NetworkState only for dashcams(); a robot device "
                        "enters the planner's fleet at arms_policy.py:639 with a literal "
                        "13.6e6 / 8.0 and 0.044, so in a mixed-fleet cell the policy would "
                        "mispredict every robot's upload while the emulator charged the real "
                        "rate",
                 blocks="the mixed-fleet cell's interpretability, not its execution"),
        ],
    )
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: res[k] for k in ("status", "why_not_posted", "blockers")},
                     indent=2, sort_keys=True))
    for s, f in fleets.items():
        print("seed", s, f["class_counts"], json.dumps(f["mixed_class_by_device"],
                                                       sort_keys=True))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
