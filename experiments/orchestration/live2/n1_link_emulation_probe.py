#!/usr/bin/env python3
"""N1 (D215): does per-device bandwidth and RTT emulation take effect in live2?

CLAUDE.md Step 2, applied to the link parameters. Two dry cells on the SAME trace, mode A,
StubCoordinator (CPU only, no model, no GPU): one at the committed uniform link (13.6 Mbit/s,
44 ms, D75) and one with EVERY device at 0.90 Mbit/s (the Irish 5G p10 of D215 Tier 1). The
second cell can only be built by passing `link_by_device` to `FleetEmulator` BY HAND, which is
the finding: no production entry point passes it.

What it reports, per cell:
  * the per-frame upload time actually charged (t_frame_arrive - t_opportunity, from
    outcomes.jsonl, which is the delivered time the scorer reads)
  * the per-recall-question upload time (the only query-side upload the emulator charges)
  * the uplink serialisation sum and queueing, from `UplinkQueue.stats()`

DIAGNOSTIC, not a bar: this digest is never used as a proof bar or a Step 2b baseline, so
D216 (1) does not require it to run alone. loadavg is recorded as a magnitude either way.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments/orchestration/policy/audit"))
import _harness as H  # noqa: E402

POOR_MBPS = 0.90          # the rate this probe injects, to show the arithmetic takes effect
QUESTION_TEXT_B = 1200    # fleet/emulator.py:73

# THE CORRECTED LABEL for the committed uniform condition (user ruling 2026-11-23, recorded at
# `75d021d3` beside the original citation in reports/study_e1_nexar_lead.md). It is NOT a US 5G
# median: per Ookla H2 2025 these are T-Mobile's figures, the HIGHEST carrier median 5G upload
# (13.57 Mbit/s) and the LOWEST carrier latency (44 ms), so the main operating point sits at the
# OPTIMISTIC END of the range rather than at its centre.
MAIN_OPERATING_POINT_LABEL = (
    "uniform 13.6 Mbit/s / 44 ms uplink: best-performing US carrier's 5G median (Ookla H2 2025), "
    "close to the 12 Mbit/s Bay Area 5G median (Khan et al. 2024)")
POOR_RATE_PROVENANCE = (
    "0.90 Mbit/s is a PROBE RATE ONLY, chosen so the injected change is large and checkable by "
    "hand. It is NOT a Tier 1 cell value: Tier 1 uplinks come from cited UPLINK sources (the "
    "StudyE1 sweep), never from the Irish 5G percentiles, which are DOWNLINK (N2).")


def loadavg() -> dict:
    a, b, c = os.getloadavg()
    return dict(load_1m=round(a, 2), load_5m=round(b, 2), load_15m=round(c, 2))


def _spread(xs):
    xs = sorted(xs)
    if not xs:
        return None
    return dict(n=len(xs), min_s=round(xs[0], 6), p50_s=round(xs[len(xs) // 2], 6),
                max_s=round(xs[-1], 6),
                mean_s=round(statistics.fmean(xs), 6))


def one_cell(tdir: Path, out: Path, mbps, rtt_ms, mode: str) -> dict:
    H.setup_paths()
    import fleet.emulator as EM
    import fleet.links as LK

    link_by_device = None
    if mbps is not None:
        devs = {json.loads(l)["device_id"] for l in open(tdir / "trace.jsonl")
                if json.loads(l)["kind"] == "device_register"}
        link_by_device = {d: LK.LinkSpec(uplink_mbps=float(mbps), rtt_ms=float(rtt_ms),
                                         downlink_mbps=float(mbps)) for d in sorted(devs)}
    em = EM.FleetEmulator(tdir, EM.StubCoordinator(capacity_per_s=8.0, service_s=0.25), mode,
                          link_by_device=link_by_device, realtime=False, drain_s=5.0)
    meta = em.run(out)
    rows = [json.loads(l) for l in open(out / "outcomes.jsonl")]

    frame_up, q_up, ser_frame, ser_hist = [], [], [], []
    for r in rows:
        if r.get("kind") == "monitor" and r.get("t_frame_arrive") is not None:
            frame_up.append(float(r["t_frame_arrive"]) - float(r["t_opportunity"]))
    for d, q in em.queues.items():
        for t in q.log:
            if t.kind == "monitor_frame":
                ser_frame.append((t.nbytes, t.t_arrive - t.t_offer))
            elif t.kind == "recall_question":
                q_up.append(t.t_arrive - t.t_offer)
            elif t.kind == "history_batch":
                ser_hist.append((t.nbytes, t.t_arrive - t.t_offer))

    applied = {d: s.as_dict() for d, s in sorted(em.links.items())}
    return dict(
        applied_link_params=applied,
        n_devices_with_link=len(applied),
        frame_bytes_mode=(statistics.mode([b for b, _ in ser_frame]) if ser_frame else None),
        per_frame_upload_delivered_s=_spread(frame_up),
        per_frame_upload_from_uplink_log_s=_spread([x for _, x in ser_frame]),
        per_question_upload_s=_spread(q_up),
        question_bytes=QUESTION_TEXT_B,
        per_history_batch_upload_s=_spread([x for _, x in ser_hist]),
        history_batch_bytes=_spread([float(b) for b, _ in ser_hist]),
        uplink_stats_by_device=meta["uplink"],
        uplink_queue_p99_s_median=meta["uplink_queue_p99_s_median"],
        run_meta={k: meta[k] for k in ("mode", "run_s", "n_devices", "ratio", "seed",
                                       "fairness_digest", "digests_equal", "n_opportunities",
                                       "n_served", "run_valid", "server_kind")},
    )


def policy_belief_cell(scratch: Path, n_dev: int, run_s: float, seed: int, ratio: str,
                       mode: str, mbps, rtt_ms) -> dict:
    """Does the emulator's LinkSpec reach the POLICY's believed link?

    The chain under test: `emulator.py:436` puts the emulator's own LinkSpec into the
    `device_register` it sends (the trace itself carries `uplink_mbps=None`, `trace.py:271`),
    `cstate.py:155` parses it, `cstate.py:311` turns it into `NetworkState.uplink_bps`, and
    `arms_policy.py:405` / `:548` turn that into the planner's `Link.bandwidth_bytes_s`, which
    `policy/coordinator.py:130` reads through `Link.up_s` to predict a delay.

    There is no injection point, so the only way to vary it in a REAL dry cell is to rebind the
    `LinkSpec` defaults in this process. That is the finding, not a workaround.
    """
    H.setup_paths()
    # `emulator.py:68` does `import links as LK`, so the module object the emulator holds is
    # `links`, NOT `fleet.links`; patching the wrong one silently leaves 13.6 in place.
    import links as LK
    if mbps is not None:
        LK.LinkSpec.__init__.__defaults__ = (float(mbps), float(rtt_ms), float(mbps))
    out = H.run_fleet_cell(scratch, n_dev, run_s=run_s, seed=seed, arm_name="policy-core",
                           ratio=ratio, mode=mode)
    co = out["coordinator"]
    devs = {}
    for sid, s in getattr(co.st, "sessions", {}).items():
        net = getattr(s, "network", None)
        if net is not None:
            devs[str(sid)] = dict(uplink_bps=getattr(net, "uplink_bps", None),
                                  rtt_s=getattr(net, "rtt_s", None),
                                  connected=getattr(net, "connected", None))
    regs = {d.device_id: dict(uplink_mbps=d.uplink_mbps, rtt_ms=d.rtt_ms)
            for d in co.st.devices.values()}
    return dict(linkspec_defaults=LK.LinkSpec.__init__.__defaults__,
                coordinator_registered_links=regs,
                believed_network_by_session=devs,
                n_decisions=len(out["decisions"]))


def grep_read_sites() -> dict:
    def g(pat, where):
        p = subprocess.run(["grep", "-rn", "--include=*.py", pat, where],
                           capture_output=True, text=True, cwd=str(ROOT))
        return [l for l in p.stdout.splitlines() if "__pycache__" not in l]
    mentions = g("link_by_device", "experiments/")
    mine = ("n1_link_emulation_probe.py", "n3_tier1_cell_definitions.py")
    prod = [l for l in mentions if not any(m in l for m in mine)]
    return dict(
        link_by_device_mentions=mentions,
        link_by_device_production_references=prod,
        link_by_device_production_reference_count=len(prod),
        link_by_device_verdict=(
            "the ONLY production references are the parameter declaration and the one write "
            "inside FleetEmulator itself; no production caller passes it. The remaining "
            "mentions are THIS SESSION's own diagnostic probe and its definitions file, which "
            "pass it BY HAND and are the reason the 0.9 Mbit/s condition could be built at all. "
            "They are listed separately so they cannot be mistaken for a caller."),
        fleetemulator_constructions=g("FleetEmulator(", "experiments/"),
        link_cli_flags=g("--uplink", "experiments/") + g("--rtt", "experiments/")
        + g("--link", "experiments/"),
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=4)
    ap.add_argument("--devices", type=int, default=16)
    ap.add_argument("--run-s", type=float, default=180.0)
    ap.add_argument("--ratio", default="50:50")
    ap.add_argument("--mode", default="A")
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--policy-belief-mbps", type=float, default=None,
                    help="instead of the two stub cells, run ONE real dry cell with the "
                         "LinkSpec defaults rebound to this rate and dump the policy's "
                         "believed link")
    a = ap.parse_args(argv)

    if a.policy_belief_mbps is not None:
        scratch = Path(a.scratch)
        scratch.mkdir(parents=True, exist_ok=True)
        res = dict(loadavg=loadavg(),
                   main_operating_point_label=MAIN_OPERATING_POINT_LABEL,
                   injected_rate_provenance=POOR_RATE_PROVENANCE,
                   belief=policy_belief_cell(scratch, a.devices, a.run_s, a.seed, a.ratio,
                                             a.mode, a.policy_belief_mbps, 44.0))
        res["loadavg_after"] = loadavg()
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, indent=2, sort_keys=True) + "\n")
        print(json.dumps(res, indent=2, sort_keys=True)[:4000])
        return 0

    scratch = Path(a.scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    load_before = loadavg()
    tdir = H.build_trace(scratch, a.devices, a.run_s, seed=a.seed, ratio=a.ratio, mode=a.mode)

    cells = {}
    cells["committed_uniform_13p6"] = one_cell(tdir, scratch / "run_13p6", None, None, a.mode)
    load_mid = loadavg()
    cells["all_devices_0p9"] = one_cell(tdir, scratch / "run_0p9", POOR_MBPS, 44.0, a.mode)
    load_after = loadavg()

    a_ = cells["committed_uniform_13p6"]["per_frame_upload_delivered_s"]
    b_ = cells["all_devices_0p9"]["per_frame_upload_delivered_s"]
    nb = cells["all_devices_0p9"]["frame_bytes_mode"]
    expected = dict(
        frame_bytes=nb,
        serialise_13p6_s=(round(nb * 8.0 / 13.6e6, 6) if nb else None),
        serialise_0p9_s=(round(nb * 8.0 / 0.9e6, 6) if nb else None),
        plus_rtt_half_s=0.022,
        predicted_total_13p6_s=(round(nb * 8.0 / 13.6e6 + 0.022, 6) if nb else None),
        predicted_total_0p9_s=(round(nb * 8.0 / 0.9e6 + 0.022, 6) if nb else None),
        bandwidth_ratio=round(13.6 / 0.9, 4),
    )
    res = dict(
        question=("N1 (D215): is per-device bandwidth and RTT emulation LIVE, CONSTANT or "
                  "ABSENT in live2?"),
        main_operating_point_label=MAIN_OPERATING_POINT_LABEL,
        injected_rate_provenance=POOR_RATE_PROVENANCE,
        cell_role="DIAGNOSTIC (not a proof bar, not a Step 2b baseline); D216 (1) alone rule "
                  "therefore not invoked",
        loadavg=dict(before=load_before, between_cells=load_mid, after=load_after),
        trace=dict(dir=str(tdir), seed=a.seed, devices=a.devices, run_s=a.run_s,
                   ratio=a.ratio, mode=a.mode,
                   frame_bytes_source=json.loads((tdir / "trace_meta.json").read_text())
                   .get("frame_bytes_source")),
        cells=cells,
        arithmetic_check=expected,
        measured_ratio_per_frame=(round(b_["p50_s"] / a_["p50_s"], 4)
                                  if a_ and b_ and a_["p50_s"] else None),
        measured_ratio_per_question=(
            round(cells["all_devices_0p9"]["per_question_upload_s"]["p50_s"]
                  / cells["committed_uniform_13p6"]["per_question_upload_s"]["p50_s"], 4)
            if cells["all_devices_0p9"]["per_question_upload_s"] else None),
        plumbing=grep_read_sites(),
    )
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: res[k] for k in ("loadavg", "arithmetic_check",
                                          "measured_ratio_per_frame",
                                          "measured_ratio_per_question")},
                     indent=2, sort_keys=True))
    for name, c in cells.items():
        print(name, json.dumps(dict(
            applied=sorted({json.dumps(v, sort_keys=True)
                            for v in c["applied_link_params"].values()}),
            frame=c["per_frame_upload_delivered_s"],
            question=c["per_question_upload_s"],
            history=c["per_history_batch_upload_s"]), sort_keys=True))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
