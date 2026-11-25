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


def test_device_sends_are_schema_valid(slice_root: Path, devs):
    """GATE 2b -- the gap the first review found.

    The old gates checked that the SERVER could build a valid event. They never checked that
    the DEVICE sends one. `_send_passthrough` used to forward the raw trace record, which
    carries the generator's own bookkeeping (duration_s, join_offset_s, joined_part_way,
    source_session on session_start) that the wire schema does not define. It survived only
    because the server rebuilt from named fields and discarded the rest -- and
    `live2/bridge.py` calls SC.parse() and is stricter than that.

    This gate captures every message the device would put on the wire and validates it.
    """
    print("\n[agent] gate 2b: every OUTBOUND device message is schema-valid")
    import device_agent as DA2

    captured = []

    class FakeWire:
        def __init__(self):
            self.bytes_sent = 0
            self.n_sent = 0

        def send(self, msg, blob=None):
            captured.append(msg)
            return 0

        def stats(self):
            return dict(n_sent=0, n_recv=0, bytes_sent=0, bytes_recv=0)

    # Drive the senders directly, with no socket and no server.
    for d in devs[:4]:
        ag = DA2.DeviceAgent.__new__(DA2.DeviceAgent)
        ag.dir = slice_root / d
        ag.meta = json.loads((ag.dir / "slice_meta.json").read_text())
        ag.device_id = str(ag.meta["device_id"])
        ag.records = [json.loads(l) for l in open(ag.dir / "trace.jsonl") if l.strip()]
        ag.profile = DA2.Profile(ag.dir / "device_answers.jsonl")
        ag.frames = DA2.FrameStore(None, True)
        fw = FakeWire()
        ag.wire = fw
        ag.t0 = time.monotonic()
        ag.speed = 1.0
        ag._stop = threading.Event()
        sent = []

        class CapturingUplink:
            def offer(self, kind, ref, msg, blob=None):
                sent.append(msg)
                return 0.0

        ag.uplink = CapturingUplink()
        deadlines = []
        for rec in ag.records:
            k = rec["kind"]
            try:
                if k == "monitor_opportunity":
                    ag._send_monitor(rec, deadlines)
                elif k == "history_batch":
                    ag._send_history(rec)
                elif k == "recall_question":
                    ag._send_recall(rec, deadlines)
                else:
                    ag._send_passthrough(rec)
            except Exception as e:
                check("%s builds every outbound event (%s)" % (d, k), False,
                      "%s: %s" % (type(e).__name__, e))
                break
        else:
            allmsgs = captured + sent
            bad = []
            for m in allmsgs:
                kind = m.get("kind")
                want = EC.OFFLINE_FIELDS.get(kind)
                if want is None:
                    bad.append("unknown kind %r" % kind)
                    continue
                extra = [f for f in m if f != "kind" and f not in want]
                if extra:
                    bad.append("%s carries %s" % (kind, extra))
            check("%s: %d outbound messages, none off-schema" % (d, len(allmsgs)),
                  not bad, "; ".join(bad[:3]))
        captured.clear()


def test_uplink_queue():
    """The FIFO uplink: queueing delay recorded SEPARATELY, per links.py."""
    print("\n[uplink] gate: FIFO queue records queue_s, never hides it")
    import device_agent as DA3

    class SlowWire:
        """A wire that takes a fixed time per send, standing in for a shaped link."""

        def __init__(self, per_send: float):
            self.per_send = per_send
            self.sent = []

        def send(self, msg, blob=None):
            time.sleep(self.per_send)
            self.sent.append((msg, len(blob) if blob else 0))

    t0 = time.monotonic()
    clock = lambda: time.monotonic() - t0          # noqa: E731
    w = SlowWire(0.02)
    up = DA3.UplinkSender(w, clock)
    up.start()
    # Offer 5 transfers back-to-back. Each takes 20 ms, so later ones MUST queue.
    for i in range(5):
        up.offer("monitor_frame", "opp%d" % i, {"kind": "monitor_frame", "i": i},
                 blob=b"x" * 1000)
    up.drain_and_stop(timeout=10.0)
    check("every offered transfer left the uplink", len(w.sent) == 5,
          "sent=%d" % len(w.sent))
    check("no sender error", up.err is None, str(up.err))
    check("one log row per transfer", len(up.log) == 5, "rows=%d" % len(up.log))
    check("FIFO order preserved",
          [m[0]["i"] for m in w.sent] == list(range(5)))
    qs = [r["queue_s"] for r in up.log]
    check("later transfers record a NON-ZERO queue_s (delay not hidden)",
          max(qs) > 0.01, "max queue_s=%.4f" % max(qs))
    check("queue_s is monotonic non-decreasing for a saturated uplink",
          qs == sorted(qs), str([round(q, 4) for q in qs]))
    check("occupancy is recorded separately from queueing",
          all(r["occupancy_s"] > 0 for r in up.log))
    st = up.stats()
    check("stats report n, busy_s and queue percentiles",
          st["n"] == 5 and st["busy_s"] > 0 and st["queue_max"] is not None)
    # A transfer must never block the OFFER side.
    w2 = SlowWire(0.05)
    up2 = DA3.UplinkSender(w2, clock)
    up2.start()
    a = time.monotonic()
    for i in range(10):
        up2.offer("monitor_frame", "o%d" % i, {"kind": "monitor_frame"}, blob=b"y" * 100)
    offer_elapsed = time.monotonic() - a
    check("offering 10 transfers does not block the replay loop",
          offer_elapsed < 0.05, "offer took %.3f s" % offer_elapsed)
    up2.drain_and_stop(timeout=10.0)


def test_cell_config():
    """A cell is one declarative object, and bad cells are refused."""
    print("\n[config] cell configs resolve, and guards refuse bad cells")
    import cell_config as CC
    import tempfile as TF

    here = Path(__file__).resolve().parent.parent
    for name in ("cell_c_5g", "cell_d_wifi6", "cell_e_unshaped", "cell_smoke_loopback"):
        p = here / "cells" / (name + ".json")
        if not p.exists():
            check("cells/%s.json exists" % name, False)
            continue
        try:
            r = CC.load(p)
            check("%s resolves (%d real + %d emulated)"
                  % (name, r["n_real"], r["n_emulated"]), True)
        except Exception as e:
            check("%s resolves" % name, False, "%s: %s" % (type(e).__name__, e))

    trace = (here / ".." / ".." / "results" / "orchestration" / "live2" / "frozen_test"
             / "traces" / "seed4_n16_1200s_A_r40-40-20_lh_req_ss2").resolve()
    base = dict(name="t", trace_dir=str(trace), run_s=1200.0,
                devices=[dict(device_id="dash000", host="orin-1", role="real",
                              profile="unshaped")])

    def refuses(label, mutate):
        c = json.loads(json.dumps(base))
        mutate(c)
        p = Path(TF.mkdtemp()) / "c.json"
        p.write_text(json.dumps(c))
        try:
            CC.load(p)
            check("refuses: " + label, False, "it was ACCEPTED")
        except CC.ConfigError:
            check("refuses: " + label, True)
        except Exception as e:
            check("refuses: " + label, False, "wrong error %s" % type(e).__name__)

    refuses("run_s shorter than the trace", lambda c: c.update(run_s=60.0))
    refuses("mode B (not implemented)", lambda c: c.update(mode="B"))
    refuses("unknown profile", lambda c: c["devices"][0].update(profile="nope"))
    refuses("host with no measured floor",
            lambda c: c["devices"][0].update(host="mystery-box"))
    refuses("missing a required key", lambda c: c.pop("run_s"))

    # The pluggability claim: a new profile AND a new host, from a FILE, no code edit.
    import shutil
    d = Path(TF.mkdtemp())
    src = here / "cells" / "profiles_example.json"
    if src.exists():
        shutil.copy(src, d / "profiles_example.json")
        c = dict(name="plug", trace_dir=str(trace), run_s=1200.0,
                 profiles_file="profiles_example.json",
                 devices=[dict(device_id="dash000", host="orin-5", role="real",
                               profile="wifi6-quiet-2client")])
        p = d / "c.json"
        p.write_text(json.dumps(c))
        try:
            r = CC.load(p)
            check("a NEW profile and host load from a config file, no code edit",
                  r["devices"][0]["shaping"]["feasible"])
        except Exception as e:
            check("a NEW profile and host load from a config file, no code edit", False,
                  "%s: %s" % (type(e).__name__, e))


def test_shaping_actuation():
    """Shaping emits real commands and refuses to apply them by default."""
    print("\n[shaping] commands are emitted; applying is refused unless confirmed")
    cmds = MP.tc_commands("5g-committed", "orin-1", "eth0")
    check("tc commands are produced", len(cmds) >= 2, "n=%d" % len(cmds))
    flat = " ".join(" ".join(c) for c in cmds)
    check("netem delay is target minus floor, halved for one-way",
          "netem delay 21.317ms" in flat, flat[:120])
    check("the uplink rate is capped", "tbf" in flat and "13600kbit" in flat)
    r = MP.apply("5g-committed", "orin-1", "eth0", confirm=False)
    check("a dry run applies NOTHING", r["applied"] is False and "refused" in r)

    seen = []
    r2 = MP.apply("5g-committed", "orin-1", "eth0", confirm=True,
                  runner=lambda c: (seen.append(c), 0)[1])
    check("confirm=True runs every command", r2["applied"] and len(seen) == len(cmds))
    check("an infeasible host is refused before any command is built",
          _refuses_infeasible())
    m = MP.mnwifi_params("wifi6-8clients", "orin-4")
    check("Mininet-WiFi params carry bw, delay and provenance",
          m["bw"] and m["delay"] and m["provenance"])
    check("orin-4's MTU 1466 is carried into the params", m["mtu"] == 1466)


def _refuses_infeasible():
    MP.PROFILES["_imposs"] = dict(rtt_ms=1.0, uplink_mbps=1.0, downlink_mbps=1.0,
                                  loss_pct=0.0, jitter_ms=0.0, one_way=False,
                                  provenance="test")
    try:
        MP.tc_commands("_imposs", "orin-1", "eth0")
        return False
    except ValueError:
        return True
    finally:
        del MP.PROFILES["_imposs"]


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

    test_shaping_actuation()
    test_cell_config()
    test_uplink_queue()
    if slice_root and devs:
        test_device_sends_are_schema_valid(slice_root, devs)
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
