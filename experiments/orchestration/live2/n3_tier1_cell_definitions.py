#!/usr/bin/env python3
"""N3 (D215 Tier 1): the three static-5G-link cell definitions, as data. NO CELLS ARE POSTED.

Tier 1 of D215 is median (all p50), poor (p10 bandwidth with high-percentile RTT) and mixed
fleet (a fixed seeded p10 / p50 / p90 assignment identical across arms). This script writes the
definitions, including the mixed-fleet assignment for seeds 4 and 5 so the fairness property can
be checked by eye, and the D215 / F12 instrumentation each cell must collect.

IT DOES NOT RUN OR POST A CELL. N1 found the per-device link has no injection point in any
production entry point (`link_by_device` is declared and defaulted in `fleet/emulator.py` and
passed by nothing), so a posted cell would be UNEXERCISED under CLAUDE.md Rule 2. The bandwidth
numbers are also BLOCKED on a user ruling: N2 established that the committed Irish 5G
percentiles are DOWNLINK (`DL_bitrate`), so every bandwidth figure below is carried as an
explicit option, not as a committed input.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments/orchestration/policy/audit"))
import _harness as H  # noqa: E402

ARMS = ("simplestream", "llf", "mooncake", "eco-llm", "confidence-cascade",
        "<final rung 3>", "<final rung 4>", "device-only")
SEEDS = (4, 5)

# N2, OBSERVED, results/orchestration/live2/network/n2_irish5g_uplink_rtt_driving.json
DL_PCT_MBIT_S = dict(p10=0.8954, p50=9.5775, p90=102.898)   # DOWNLINK, not uplink
RTT_PCT_MS = dict(p50=80.0, p90=120.0, p99=351.35)          # PINGAVG, direction-agnostic
UL_COLUMN_PCT_MBIT_S = dict(p10=0.017, p50=0.093, p90=0.2337)  # ACK traffic, NOT capacity

COMMITTED_UNIFORM = dict(uplink_mbps=13.6, rtt_ms=44.0, source="D75 / StudyE4 / E9 / CTRL1c")


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


def mixed_assignment(seed: int, ids):
    """A FIXED seeded assignment of the three speed classes, IDENTICAL ACROSS ARMS.

    It is a function of (seed, sorted device roster) only: no arm, no run, no wall clock enters
    it, which is the fairness property D215 asks for. Thirds in sorted order after one seeded
    shuffle, so the class counts are as equal as 16 allows (6 / 5 / 5 at 16 devices).
    """
    ids = sorted(ids)
    order = list(ids)
    random.Random(("tier1-mixed-5g", int(seed))).shuffle(order)
    classes = ("p10", "p50", "p90")
    out = {}
    for i, d in enumerate(order):
        out[d] = classes[i % 3]
    return {d: out[d] for d in ids}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--devices", type=int, default=16)
    ap.add_argument("--ratio", default="50:50")
    ap.add_argument("--run-s", type=float, default=1200.0)
    ap.add_argument("--mode", default="A")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    fleets = {}
    for s in SEEDS:
        ids, types, src = roster(s, a.devices, a.ratio, a.run_s, a.mode)
        asg = mixed_assignment(s, ids)
        fleets[str(s)] = dict(
            device_ids=sorted(ids), types=types, roster_source=src,
            mixed_class_by_device=asg,
            class_counts={c: sum(1 for v in asg.values() if v == c)
                          for c in ("p10", "p50", "p90")})

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

    cells = dict(
        median=dict(
            definition="every device at the p50 bandwidth and p50 RTT",
            rtt_ms=RTT_PCT_MS["p50"], rtt_register="OBSERVED (PINGAVG p50)",
            bandwidth_mbit_s_OPTION_A=DL_PCT_MBIT_S["p50"],
            bandwidth_register="BLOCKED: option A reuses the DOWNLINK p50 as a symmetric-link "
                               "ASSUMPTION; see blockers"),
        poor=dict(
            definition="every device at the p10 bandwidth with the p90 RTT; p99 RTT reported "
                       "beside it as D215 asks",
            rtt_ms=RTT_PCT_MS["p90"], rtt_p99_ms=RTT_PCT_MS["p99"],
            rtt_register="OBSERVED (PINGAVG p90 and p99)",
            bandwidth_mbit_s_OPTION_A=DL_PCT_MBIT_S["p10"],
            bandwidth_register="BLOCKED, as for median",
            expected_scale="at 0.90 Mbit/s one 63,898 B dashcam JPEG serialises in 0.568 s and "
                           "arrives 0.590 s after capture on an idle uplink; at 16 devices the "
                           "uplink SATURATES and the measured median per-frame upload is 6.34 s "
                           "(N1 probe)"),
        mixed_fleet=dict(
            definition="a FIXED SEEDED p10 / p50 / p90 assignment, a function of (seed, sorted "
                       "device roster) only, so it is IDENTICAL ACROSS ARMS",
            rtt_ms_by_class=dict(p10=RTT_PCT_MS["p90"], p50=RTT_PCT_MS["p50"],
                                 p90=RTT_PCT_MS["p50"]),
            rtt_register="CONSTRUCTED: pairing the slow class with the high-percentile RTT is a "
                         "modelling choice, not a measured joint distribution",
            bandwidth_mbit_s_by_class_OPTION_A=DL_PCT_MBIT_S,
            bandwidth_register="BLOCKED, as for median",
            fleets=fleets),
    )

    res = dict(
        status="DEFINITIONS ONLY. NOT POSTED TO THE H100.",
        why_not_posted=("N1: the per-device link has NO injection point. `link_by_device` is "
                        "declared at fleet/emulator.py:245 and written at :291 and is passed by "
                        "no caller anywhere in experiments/, so every cell runs at the single "
                        "process-wide LinkSpec() default (13.6 Mbit/s, 44 ms). A posted cell "
                        "would differ from the main operating point in nothing, and a flat "
                        "result would be UNEXERCISED under CLAUDE.md Rule 2, not a finding."),
        arms=list(ARMS), seeds=list(SEEDS),
        seeds_note="seeds 4 and 5 only; never seeds 1 to 3 and never HOLDOUT",
        fleet=dict(n_devices=a.devices, ratio=a.ratio, run_s=a.run_s, mode=a.mode,
                   note="ratio and run_s carried over from the main operating point; confirm "
                        "against the D212 grid definition rather than assuming"),
        queue=dict(d212="all baseline cells are FILLER; policy cells always run first; the H100 "
                        "gates posted lists in order"),
        committed_uniform_link=COMMITTED_UNIFORM,
        cells=cells,
        instrumentation_D215_F12=instrumentation,
        blockers=[
            dict(id="B1", what="per-device link emulation has no injection point",
                 detail="no CLI flag, no caller of link_by_device, and fleet/trace.py emits "
                        "device_register with uplink_mbps=None, rtt_ms=None (:496, :591, :639), "
                        "which the emulator overwrites from its own LinkSpec at :476",
                 blocks="all three cells"),
            dict(id="B2", what="the committed 5G percentiles are DOWNLINK",
                 detail="e31_network.py:84 reads row['DL_bitrate']; results/INDEX.md:229 says so "
                        "in words; the UL_bitrate column exists but every subset of the dataset "
                        "is a DOWNLOAD workload, so its p10/p50/p90 of %s Mbit/s is ACK traffic, "
                        "not uplink capacity" % (UL_COLUMN_PCT_MBIT_S,),
                 blocks="every bandwidth number in all three cells; needs a user ruling"),
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
