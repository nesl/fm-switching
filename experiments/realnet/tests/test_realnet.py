#!/usr/bin/env python3
"""Unit and integration gates for StudyREAL-NET. No lab device is touched.

Run:  python3 tests/test_realnet.py --trace-dir <frozen trace>

Each gate is a check that CAN FAIL, per the repo's D92/D225 discipline, not a demonstration.
Gate 7 (the negative control) is the one that distinguishes "real devices changed the result"
from "our new code changed the result"; it needs two cells and so is marked as a run-time
gate, not a unit test.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import device_agent as DA          # noqa: E402
import emulated_fleet_client as FC  # noqa: E402
import events_check as EC          # noqa: E402
import mnwifi_profiles as MP       # noqa: E402
import slice_trace as ST           # noqa: E402
import wire as W                   # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print("  %-58s %s%s" % (name, "PASS" if ok else "FAIL",
                            ("  " + detail) if detail and not ok else ""))
    return bool(ok)


# ---------------------------------------------------------------- wire
def test_wire():
    print("\n[wire] framing")
    a, b = socket.socketpair()
    wa, wb = W.Wire(a), W.Wire(b)
    wa.send({"kind": "x", "n": 1})
    m, blob = wb.recv()
    check("plain message round-trips", m["kind"] == "x" and m["n"] == 1 and blob is None)

    # A socketpair's buffer is smaller than 59,601 B, so sendall() blocks until a reader
    # drains it. Send from a thread: otherwise this test deadlocks on the very payload size
    # the study uses. (The real server always has a concurrent reader, so this is a property
    # of the test harness, not of Wire.)
    payload = os.urandom(59601)
    err = []

    def _send():
        try:
            wa.send({"kind": "monitor_frame", "frame_bytes": len(payload)}, blob=payload)
        except Exception as e:  # pragma: no cover - surfaced via the check below
            err.append("%s: %s" % (type(e).__name__, e))

    th = threading.Thread(target=_send, name="blob-send")
    th.daemon = True
    th.start()
    m, blob = wb.recv()
    th.join(timeout=10)
    check("59,601 B blob send did not error", not err, "; ".join(err))
    check("59,601 B blob round-trips byte-for-byte", blob == payload)
    check("blob length is declared on the wire", m[W.BLOB_KEY] == 59601)

    # Real bytes, not base64: the wire cost must equal the payload plus one short line.
    overhead = wa.bytes_sent - 59601 - 20
    check("no base64 inflation (overhead < 200 B)", overhead < 200, "overhead=%d" % overhead)

    for i in range(5):
        wa.send({"kind": "k%d" % i}, blob=bytes([i]) * (i + 1))
    got = [wb.recv() for _ in range(5)]
    check("5 pipelined messages arrive in order",
          [g[0]["kind"] for g in got] == ["k%d" % i for i in range(5)])
    check("each pipelined blob is intact",
          all(got[i][1] == bytes([i]) * (i + 1) for i in range(5)))

    wa.close()
    try:
        wb.recv()
        check("clean close raises EOFError", False)
    except EOFError:
        check("clean close raises EOFError", True)
    except Exception as e:
        check("clean close raises EOFError", False, type(e).__name__)
    wb.close()


# ---------------------------------------------------------------- schema
def test_schema():
    print("\n[schema] our mirror vs the repo's own events.py")
    d = EC.check_drift()
    check("repo events.py is reachable", d.get("checked"), d.get("reason", ""))
    if d.get("checked"):
        check("zero field drift", not d.get("field_diffs"), str(d.get("field_diffs"))[:120])
        check("zero optional-field drift", not d.get("optional_diffs"))

    # A malformed event must FAIL LOUDLY, never be coerced (gate 2).
    try:
        EC.make("monitor_frame", device_id="d", opportunity_id="o")
        check("missing required fields raise", False)
    except Exception:
        check("missing required fields raise", True)
    try:
        EC.make("monitor_frame", device_id="d", opportunity_id="o", instant_id="i",
                t_capture=0.0, t_arrive=0.0, deadline_s=1.0, frame_ref="f",
                frame_bytes=1, bogus_field=1)
        check("unknown field raises", False)
    except Exception:
        check("unknown field raises", True)
    try:
        EC.make("device_register", device_id="d", type="toaster",
                uplink_mbps=None, rtt_ms=None, start_t=0.0)
        check("invalid device type raises", False)
    except Exception:
        check("invalid device type raises", True)


# ---------------------------------------------------------------- profiles
def test_profiles():
    print("\n[profiles] feasibility arithmetic")
    f = MP.feasible("wifi6-quiet", "orin-1")
    check("wifi6-quiet feasible on orin-1", f["feasible"])
    check("shaping offset is target minus floor p50",
          abs(f["add_rtt_ms"] - (3.6 - 1.366)) < 1e-6, str(f["add_rtt_ms"]))
    check("feasibility tests floor p99 against target",
          f["floor_p99_ms"] == MP.FLOOR_RT_MS["orin-1"]["p99"])
    check("orin-4 MTU is recorded as 1466", MP.MTU["orin-4"] == 1466)

    # An infeasible case must be reported as such, not quietly clamped.
    MP.PROFILES["_test_impossible"] = dict(rtt_ms=1.0, uplink_mbps=1.0, downlink_mbps=1.0,
                                           loss_pct=0.0, jitter_ms=0.0, one_way=False,
                                           provenance="test only")
    g = MP.feasible("_test_impossible", "orin-1")
    check("a target below the floor is reported INFEASIBLE", not g["feasible"])
    del MP.PROFILES["_test_impossible"]

    check("unshaped profile adds nothing", MP.feasible("unshaped", "flash")["add_rtt_ms"] == 0.0)
    wifi = [n for n in MP.PROFILES if n.startswith("wifi6")]
    check("every wifi6 profile records one-way provenance",
          all(MP.PROFILES[n].get("one_way") and MP.PROFILES[n].get("one_way_ms")
              for n in wifi))
    check("every profile carries provenance",
          all(MP.PROFILES[n].get("provenance") for n in MP.PROFILES))


# ---------------------------------------------------------------- slicer
def test_slicer(trace_dir: Path, out_root: Path):
    print("\n[slicer] gate 1: reunion")
    loaded = ST.load_trace(trace_dir)
    parts = ST.split(loaded)
    gate = ST.verify_reunion(loaded, parts)
    check("record count preserved", gate["count_ok"])
    check("every record identical (multiset)", gate["multiset_ok"])
    check("fairness digest preserved", gate["digest_ok"])
    check("every opportunity_id in exactly one slice", gate["opportunity_ok"])
    check("no orphan records", not parts["orphans"])
    check("D96(1): no opportunity_id invented",
          gate["n_opportunities_input"] == gate["n_opportunities_sliced"])

    # Determinism: slicing twice gives the same digest.
    g2 = ST.verify_reunion(loaded, ST.split(loaded))
    check("slicing is deterministic", g2["digest_reunion"] == gate["digest_reunion"])

    ST.write_slices(parts, loaded, out_root)
    devs = sorted(p.name for p in out_root.iterdir() if p.is_dir())
    check("16 slices written", len(devs) == 16, "got %d" % len(devs))
    return devs


# ---------------------------------------------------------------- agent
def test_agent(slice_root: Path, devs):
    print("\n[agent] gate 3: slice selftest per device type")
    by_type = {}
    for d in devs:
        m = json.loads((slice_root / d / "slice_meta.json").read_text())
        by_type.setdefault(m.get("type"), d)
    for t, d in sorted(by_type.items()):
        rc = DA.selftest(slice_root / d)
        check("selftest passes for %s (%s)" % (d, t), rc == 0)

    # D201: a profiled answer must never be substituted with a neutral value.
    p = DA.Profile(slice_root / by_type[sorted(by_type)[0]] / "device_answers.jsonl")
    try:
        p.answer("opp-that-does-not-exist")
        check("D201: missing profiled answer RAISES", False)
    except KeyError:
        check("D201: missing profiled answer RAISES", True)

    # Synthetic frames must be the exact recorded length, and deterministic.
    fs = DA.FrameStore(None, synthetic=True)
    b1 = fs.get("clip|t1", 59601)
    b2 = fs.get("clip|t1", 59601)
    check("synthetic frame has the exact recorded length", len(b1) == 59601)
    check("synthetic frame is deterministic in the ref", b1 == b2)
    check("different refs give different bytes", fs.get("clip|t2", 59601) != b1)


# ---------------------------------------------------------------- integration
def test_integration(slice_root: Path, port: int, devices, run_s: float, speed: float):
    print("\n[integration] loopback against live2's own StubCoordinator")
    import net_fleet_server as S
    try:
        coord = S.build_stub()
    except Exception as e:
        check("StubCoordinator imports from live2", False, "%s: %s" % (type(e).__name__, e))
        return
    check("StubCoordinator imports from live2", True)
    check("stub satisfies the 2-method Protocol",
          callable(getattr(coord, "on_event", None)) and callable(getattr(coord, "tick", None)))

    out = Path(tempfile.mkdtemp(prefix="realnet_itest_"))
    srv = S.NetFleetServer(coord, len(devices), run_s, port, 0.010, 2.0, 60.0)
    box = {}

    def run_srv():
        try:
            box["summary"] = srv.run(out)
        except Exception as e:
            box["error"] = "%s: %s" % (type(e).__name__, e)

    th = threading.Thread(target=run_srv, name="srv")
    th.daemon = True
    th.start()
    time.sleep(1.5)

    fr = FC.FleetRunner(slice_root, devices, "127.0.0.1", port,
                        None, True, speed)
    cl = fr.run(out)
    th.join(timeout=run_s / speed + 60)

    if "error" in box:
        check("server completed", False, box["error"])
        return
    s = box.get("summary") or {}
    check("server completed", bool(s))
    check("all clients connected and finished", cl["n_failed"] == 0, str(cl["failures"])[:150])
    check("no server errors", s.get("n_errors") == 0, str(s.get("errors"))[:150])
    check("every expected device registered", s.get("n_devices") == len(devices))
    check("no unroutable replies", s.get("n_unroutable_replies") == 0)
    check("events reached the coordinator", s.get("n_events", 0) > 0)
    check("coordinator issued replies", s.get("n_replies", 0) > 0)
    check("opportunities were resolved", cl["n_resolved"] > 0)
    check("both branches exercised (cloud AND device fallback)",
          cl["n_cloud"] > 0 and cl["n_device"] > 0,
          "cloud=%s device=%s" % (cl["n_cloud"], cl["n_device"]))

    # Gate 6: a stub run must never be mistaken for a measurement.
    check("gate 6: server_kind is 'stub'", s.get("server_kind") == "stub")
    check("gate 6: is_measurement is False", s.get("is_measurement") is False)

    # Gate 5: no opportunity_id invented at run time.
    logged = set()
    for p in out.glob("device_log_*.jsonl"):
        for ln in open(p):
            if ln.strip():
                logged.add(json.loads(ln)["opportunity_id"])
    intrace = set()
    for d in devices:
        for ln in open(slice_root / d / "trace.jsonl"):
            r = json.loads(ln)
            if r.get("opportunity_id"):
                intrace.add(str(r["opportunity_id"]))
    check("gate 5: no opportunity_id invented at run time", not (logged - intrace),
          "invented=%d" % len(logged - intrace))

    # Gate 4 is reported, NOT asserted, on a laptop: the control run below shows the host's
    # own scheduler tail exceeds the harness's, so a Mac number is not a timing measurement.
    lat = s.get("lateness") or {}
    print("     gate 4 (reported, not asserted here): p50=%s ms p99=%s ms max=%s ms gate_pass=%s"
          % (lat.get("p50_ms"), lat.get("p99_ms"), lat.get("max_ms"), lat.get("gate_pass")))


def test_host_timing_control():
    print("\n[control] the host's own scheduler tail, no sockets, no coordinator")
    t0 = time.monotonic()
    nxt = 0.0
    late = []
    while nxt < 3.0:
        d = (t0 + nxt) - time.monotonic()
        if d > 0:
            time.sleep(d)
        late.append(max(0.0, (time.monotonic() - t0) - nxt))
        nxt = round(nxt + 0.010, 9)
    late.sort()
    n = len(late)
    p99 = late[int(n * 0.99)] * 1e3
    print("     bare 10 ms sleep loop: p50=%.2f ms p99=%.2f ms max=%.2f ms over10ms=%d/%d"
          % (late[n // 2] * 1e3, p99, late[-1] * 1e3,
             sum(1 for x in late if x > 0.010), n))
    print("     => a tick p99 at or below this is the host, not the harness.")
    return p99


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace-dir", default=None)
    ap.add_argument("--port", type=int, default=47950)
    ap.add_argument("--run-s", type=float, default=60.0)
    ap.add_argument("--speed", type=float, default=20.0)
    ap.add_argument("--skip-integration", action="store_true")
    a = ap.parse_args(argv)

    print("StudyREAL-NET test suite -- no lab device is touched")
    print("python %s on %s" % (sys.version.split()[0], sys.platform))

    test_wire()
    test_schema()
    test_profiles()

    slice_root = None
    devs = None
    if a.trace_dir:
        tmp = Path(tempfile.mkdtemp(prefix="realnet_slices_"))
        devs = test_slicer(Path(a.trace_dir), tmp)
        slice_root = tmp
        test_agent(slice_root, devs)
    else:
        print("\n[slicer/agent] SKIPPED: no --trace-dir given")

    if slice_root and not a.skip_integration:
        test_integration(slice_root, a.port,
                         ["dash000", "robo000", "asst000"], a.run_s, a.speed)
    test_host_timing_control()

    n = len(RESULTS)
    bad = [r for r in RESULTS if not r[1]]
    print("\n%s" % ("=" * 68))
    print("%d/%d checks pass" % (n - len(bad), n))
    for name, _ok, detail in bad:
        print("  FAILED: %s  %s" % (name, detail))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
