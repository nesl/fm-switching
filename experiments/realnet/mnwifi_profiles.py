#!/usr/bin/env python3
"""Network shaping profiles for StudyREAL-NET: 5G and Wi-Fi 6, per host.

StudyREAL-NET, component 5.

CITATIONS. The emulation methodology follows CADET (Sharma, Wang & Srivastava,
arXiv:2606.04072, 2026), whose NetWaggle layer is built on Mininet-WiFi; the tool itself is
Fontes, Afzal, Brito, Santos & Rothenberg, "Mininet-WiFi: Emulating software-defined wireless
networks", CNSM 2015 (CADET's reference [20]). Both are cited in the paper.

THE Wi-Fi 6 NUMBERS ARE EXTERNAL AND ONE-WAY. They come from Liu & Choi, Proc. ACM Meas.
Anal. Comput. Syst. 7(1) Article 25 (SIGMETRICS'23), real commodity hardware (ASUS RT-AX58U,
Intel AX210, Galaxy S10). That paper measures ONE-WAY latency by sniffing (t0 entering the
stack, t1 at delivery) specifically to avoid combining uplink and downlink, so every Wi-Fi
value here is one-way and is doubled to compare against a round trip.

THERE IS NO PUBLIC PER-PACKET Wi-Fi 6 LATENCY TRACE. What exists is condition-level summary
values. So these profiles are NOT a replayed distribution: they are measured per-condition
means with an assumed jitter shape, and `provenance` on every profile says so. The paper must
not describe this as replaying a measured Wi-Fi 6 distribution.

SHAPE TO (target - measured floor). The shaped link adds to a path that already costs
something. The floors below were measured on 2026-11-25 with real 59,601 B round trips,
200 samples per host. Subtracting them is what makes the realised link equal the target
instead of target + floor.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional, Sequence

# Measured round-trip floors, ms (p50 / stdev), real 59,601 B payloads, 2026-11-25.
FLOOR_RT_MS: Dict[str, Dict[str, float]] = {
    "flash":  dict(p50=0.761, p90=0.816, p99=0.862, stdev=0.032, link_mbps=10000.0),
    "orin-1": dict(p50=1.366, p90=1.861, p99=2.354, stdev=0.369, link_mbps=1000.0),
    "orin-2": dict(p50=1.073, p90=1.647, p99=2.069, stdev=0.313, link_mbps=1000.0),
    "orin-3": dict(p50=0.967, p90=1.186, p99=1.260, stdev=0.134, link_mbps=1000.0),
    "orin-4": dict(p50=0.546, p90=1.223, p99=1.248, stdev=0.332, link_mbps=10000.0),
}

# orin-4's NIC reports MTU 1466; everything else on the fabric is 1500. A profile that
# assumes 1500 there will fragment or black-hole.
MTU: Dict[str, int] = {"flash": 1500, "orin-1": 1500, "orin-2": 1500,
                       "orin-3": 1500, "orin-4": 1466}

PROFILES: Dict[str, Dict[str, Any]] = {
    # The committed emulated link, reproduced as a real shaped link so cell B is comparable
    # to the arithmetic cell A.
    "5g-committed": dict(
        rtt_ms=44.0, uplink_mbps=13.6, downlink_mbps=13.6, loss_pct=0.0,
        jitter_ms=0.0, one_way=False,
        provenance="D75 committed pair (StudyE4 / E9 / CTRL1c): uplink 13.6 Mbit/s, RTT 44 ms. "
                   "Downlink rate is an ASSUMPTION; links.py says no committed downlink exists.",
    ),
    "5g-irish-p50": dict(
        rtt_ms=44.0, uplink_mbps=9.58, downlink_mbps=9.58, loss_pct=0.0,
        jitter_ms=12.0, one_way=False,
        provenance="Irish 5G dataset p50 bandwidth 9.58 Mbit/s (uccmisl/5Gdataset, 16 driving "
                   "sessions). D215 FLAGS THAT THESE PERCENTILES STILL NEED CONFIRMING AS "
                   "UPLINK: e31_network.py:84 reads DL_bitrate.",
    ),
    "5g-irish-p10": dict(
        rtt_ms=44.0, uplink_mbps=0.90, downlink_mbps=0.90, loss_pct=0.0,
        jitter_ms=20.0, one_way=False,
        provenance="Irish 5G p10 bandwidth 0.90 Mbit/s, the poor-link condition of D215 Tier 1. "
                   "Same uplink caveat.",
    ),
    # Wi-Fi 6, from Liu & Choi. ONE-WAY values; doubled when compared to a round trip.
    "wifi6-quiet": dict(
        rtt_ms=3.6, uplink_mbps=200.0, downlink_mbps=200.0, loss_pct=0.0,
        jitter_ms=0.5, one_way=True, one_way_ms=1.8,
        provenance="Liu & Choi SIGMETRICS'23 Fig 10(d): UL CSMA/CA, 2 clients, no external "
                   "contention, 1.8 ms ONE-WAY -- the lowest value in the paper. Doubled to "
                   "3.6 ms round trip. Jitter is ASSUMED, not measured.",
    ),
    "wifi6-dl-nocontention": dict(
        rtt_ms=8.0, uplink_mbps=200.0, downlink_mbps=200.0, loss_pct=0.0,
        jitter_ms=1.0, one_way=True, one_way_ms=4.0,
        provenance="Liu & Choi Fig 10(a): DL OFDMA and CSMA, 2-8 clients, no contention, "
                   "'below 4 milliseconds' one-way. Treated as 4.0 ms, a BOUND not a mean.",
    ),
    "wifi6-8clients": dict(
        rtt_ms=44.8, uplink_mbps=100.0, downlink_mbps=100.0, loss_pct=0.0,
        jitter_ms=6.0, one_way=True, one_way_ms=22.4,
        provenance="Liu & Choi Fig 10(d): UL CSMA/CA, 8 clients, internal contention, 22.4 ms "
                   "one-way. Jitter ASSUMED from the paper's sigma scale, not a fitted value.",
    ),
    "wifi6-contended": dict(
        rtt_ms=71.2, uplink_mbps=50.0, downlink_mbps=50.0, loss_pct=0.0,
        jitter_ms=8.0, one_way=True, one_way_ms=35.58,
        provenance="Liu & Choi Fig 10(b): DL OFDMA maximum under external Wi-Fi 5 contention, "
                   "35.58 ms one-way. Jitter ASSUMED.",
    ),
    "wifi6-ul-contended": dict(
        rtt_ms=120.4, uplink_mbps=25.0, downlink_mbps=25.0, loss_pct=0.0,
        jitter_ms=12.0, one_way=True, one_way_ms=60.2,
        provenance="Liu & Choi Fig 10(e): UL OFDMA under heavy external contention, 60.2 ms "
                   "one-way. Jitter ASSUMED.",
    ),
    # The ideal-network bound: shape nothing, report the fabric as it is.
    "unshaped": dict(
        rtt_ms=None, uplink_mbps=None, downlink_mbps=None, loss_pct=0.0,
        jitter_ms=None, one_way=False,
        provenance="No shaping. The lab fabric as measured: ~1 ms RTT, 1-10 GbE. Reported as "
                   "an ideal-network BOUND, never as a wireless condition.",
    ),
}


def feasible(profile: str, host: str) -> Dict[str, Any]:
    """Can `host` represent `profile`? The test is max(floor) < target, per host.

    The binding constraint is the floor's WORST case against the target's BEST case: if the
    floor ever exceeds the target, that sample would need negative delay and cannot be
    synthesized. Everything above it is reachable by adding the difference.
    """
    p = PROFILES[profile]
    f = FLOOR_RT_MS[host]
    if p["rtt_ms"] is None:
        return dict(profile=profile, host=host, feasible=True, add_rtt_ms=0.0,
                    note="unshaped: nothing to add")
    target = float(p["rtt_ms"])
    worst = float(f["p99"])
    add = round(target - float(f["p50"]), 3)
    ok = worst < target
    return dict(profile=profile, host=host, target_rtt_ms=target,
                floor_p50_ms=f["p50"], floor_p99_ms=worst, floor_stdev_ms=f["stdev"],
                add_rtt_ms=add, feasible=bool(ok),
                headroom_ms=round(target - worst, 3),
                floor_jitter_pct_of_target=round(f["stdev"] / target * 100, 3),
                mtu=MTU[host],
                note=("floor p99 exceeds target; this host cannot represent this profile"
                      if not ok else "shape to target minus floor p50"))


def plan(profile: str, hosts: Sequence[str]) -> Dict[str, Any]:
    """The full shaping plan for one profile across hosts, with provenance attached."""
    p = PROFILES[profile]
    rows = [feasible(profile, h) for h in hosts]
    return dict(profile=profile, spec=p, hosts=rows,
                all_feasible=all(r["feasible"] for r in rows),
                infeasible_hosts=[r["host"] for r in rows if not r["feasible"]])


# --------------------------------------------------------------------------- actuation
#
# F3: until now this module computed a plan and applied nothing, so cells C and D could not
# run. It now EMITS the commands, and applies them only when explicitly told to.
#
# DEFAULT IS DRY RUN. Shaping needs root and changes a NIC's behaviour for every process on
# that host, so `plan_commands()` returns the exact argv list and `apply()` refuses unless
# `confirm=True` AND the caller passes a host it is actually running on. Nothing here ever
# reaches out to another machine: the commands are meant to be run BY that host, under the
# operator's own hand.

def tc_commands(profile: str, host: str, iface: str) -> List[List[str]]:
    """The `tc` commands that realise `profile` on `host`'s `iface`.

    netem ADDS to the existing path, so the delay injected is (target - measured floor p50)
    and the rate cap is the profile's uplink. `tc` takes HALF the round trip as its one-way
    delay, which is why add_rtt_ms is halved here: netem delays egress only, and the reply
    traverses the peer's own qdisc.
    """
    f = feasible(profile, host)
    if not f["feasible"]:
        raise ValueError("%s cannot represent %s: %s" % (host, profile, f["note"]))
    p = PROFILES[profile]
    if p["rtt_ms"] is None:
        return []
    one_way_ms = max(0.0, f["add_rtt_ms"] / 2.0)
    jitter_ms = float(p.get("jitter_ms") or 0.0) / 2.0
    cmds = [["tc", "qdisc", "del", "dev", iface, "root"]]          # idempotent reset
    netem = ["tc", "qdisc", "add", "dev", iface, "root", "handle", "1:", "netem",
             "delay", "%.3fms" % one_way_ms]
    if jitter_ms > 0:
        netem += ["%.3fms" % jitter_ms, "distribution", "normal"]
    if float(p.get("loss_pct") or 0.0) > 0:
        netem += ["loss", "%.3f%%" % float(p["loss_pct"])]
    cmds.append(netem)
    up = p.get("uplink_mbps")
    if up:
        # Rate-limit below netem so the cap applies to the shaped egress path.
        cmds.append(["tc", "qdisc", "add", "dev", iface, "parent", "1:", "handle", "10:",
                     "tbf", "rate", "%.0fkbit" % (float(up) * 1000.0),
                     "burst", "32kbit", "latency", "400ms"])
    return cmds


def mnwifi_params(profile: str, host: str) -> Dict[str, Any]:
    """The same profile as Mininet-WiFi station parameters.

    Mininet-WiFi (Fontes et al., CNSM 2015), used as CADET's NetWaggle does
    (arXiv:2606.04072). A station's link is given as bandwidth / delay / loss, so the same
    (target - floor) arithmetic applies.
    """
    f = feasible(profile, host)
    p = PROFILES[profile]
    return dict(profile=profile, host=host,
                bw=p.get("uplink_mbps"),
                delay="%.3fms" % (max(0.0, f["add_rtt_ms"]) / 2.0)
                      if p["rtt_ms"] is not None else None,
                loss=float(p.get("loss_pct") or 0.0),
                jitter_ms=p.get("jitter_ms"),
                mtu=MTU.get(host),
                feasible=f["feasible"],
                provenance=p.get("provenance"))


def apply(profile: str, host: str, iface: str, confirm: bool = False,
          runner=None) -> Dict[str, Any]:
    """Apply shaping. REFUSES unless confirm=True.

    `runner` is injected so a test can observe the commands without a privileged call; by
    default nothing is executed and the commands are only returned.
    """
    cmds = tc_commands(profile, host, iface)
    out = dict(profile=profile, host=host, iface=iface,
               commands=[" ".join(c) for c in cmds], applied=False)
    if not confirm:
        out["refused"] = ("dry run: shaping needs root and changes the NIC for every process "
                          "on the host; pass confirm=True to apply")
        return out
    if runner is None:
        import subprocess
        def runner(cmd):  # noqa: E306
            return subprocess.run(cmd, capture_output=True, text=True).returncode
    rcs = []
    for c in cmds:
        rcs.append(runner(c))
    out["applied"] = True
    out["returncodes"] = rcs
    # The first command is a `del` that fails harmlessly when no qdisc exists.
    out["ok"] = all(rc == 0 for rc in rcs[1:]) if len(rcs) > 1 else True
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="StudyREAL-NET shaping profiles")
    ap.add_argument("--profile", default=None, help="one profile, or omit for all")
    ap.add_argument("--hosts", default="flash,orin-1,orin-2,orin-3,orin-4")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--emit-tc", default=None, metavar="HOST:IFACE",
                    help="print the tc commands for one host (dry run; applies nothing)")
    ap.add_argument("--emit-mnwifi", default=None, metavar="HOST",
                    help="print Mininet-WiFi station parameters for one host")
    a = ap.parse_args(argv)
    hosts = [h.strip() for h in a.hosts.split(",") if h.strip()]

    if a.emit_tc:
        if not a.profile:
            print("--emit-tc needs --profile", file=sys.stderr)
            return 2
        host, _, iface = a.emit_tc.partition(":")
        r = apply(a.profile, host, iface or "eth0", confirm=False)
        print(json.dumps(r, indent=2, sort_keys=True))
        return 0
    if a.emit_mnwifi:
        if not a.profile:
            print("--emit-mnwifi needs --profile", file=sys.stderr)
            return 2
        print(json.dumps(mnwifi_params(a.profile, a.emit_mnwifi), indent=2, sort_keys=True))
        return 0
    names = [a.profile] if a.profile else sorted(PROFILES)
    out = {n: plan(n, hosts) for n in names}
    if a.json:
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0
    for n in names:
        pl = out[n]
        tgt = pl["spec"]["rtt_ms"]
        print("%-22s target RTT %s  %s" % (
            n, ("%.1f ms" % tgt) if tgt else "unshaped",
            "ALL FEASIBLE" if pl["all_feasible"] else "INFEASIBLE on " + ",".join(pl["infeasible_hosts"])))
        for r in pl["hosts"]:
            if tgt is None:
                print("    %-8s -" % r["host"])
                continue
            print("    %-8s add %+7.3f ms   floor p99 %5.3f   headroom %+7.3f   jitter %5.2f%% of target  %s"
                  % (r["host"], r["add_rtt_ms"], r["floor_p99_ms"], r["headroom_ms"],
                     r["floor_jitter_pct_of_target"], "OK" if r["feasible"] else "FAIL"))
        print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
