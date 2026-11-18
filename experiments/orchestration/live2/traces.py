#!/usr/bin/env python3
"""Traces for the flash tests. CPU only.

Two sources, and the run header always says WHICH:

  * `load(path)`  reads a JSONL trace produced by the fleet (StudyLIVE2-fleet). Its label is
                  whatever the trace file declares.
  * `synthetic()` builds a trace that conforms to `schema.py` and is labelled SYNTHETIC. It is
                  a TEST FIXTURE: its instant cadence, batch period and token arithmetic follow
                  the committed structure, but no clip, session or question in it is real, and
                  its frame files are PLACEHOLDER BYTES, not JPEGs. A synthetic trace may be run
                  only against the CPU stub, which `require_fake_server` enforces.

FAIRNESS (D69): the opportunity stream is identical for every arm. `digest` is taken over the
opportunities themselves, the same way `live/adapter.py::trace_digest` does it, and the run
header carries it so a cell with two different digests cannot be compared by accident.
"""
import hashlib
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

import schema as SC                                                   # noqa: E402

try:
    sys.path.insert(0, str(HERE / "fleet"))
    from data_sources import (D2_HEADER_TOK, D2_STRIDE_S, D2_TOK_PER_IMG,   # noqa: E402
                              E10A_NEXAR_Q90_MEDIAN_B, NEXAR_INSTANT_CADENCE_S)
    _SOURCES = "live2/fleet/data_sources.py committed constants"
except Exception:                                                     # noqa: BLE001
    D2_TOK_PER_IMG, D2_HEADER_TOK, D2_STRIDE_S = 90, 31, 2.0
    NEXAR_INSTANT_CADENCE_S = 0.5
    E10A_NEXAR_Q90_MEDIAN_B = 60_000
    _SOURCES = "live2/traces.py fallback constants (StudyRH4, StudyCTRL1c, StudyE10a)"

BATCH_PERIOD_S = 30.0          # D68: history frames uploaded in fixed batches every 30 s
UPLINK_MBPS = 13.6             # D75
RTT_MS = 44.0                  # D75
DASHCAM_L_S = 1.0              # D71
ROBOT_L_S = 5.0                # D71, D82


class SyntheticTraceRefused(RuntimeError):
    pass


# D96 part 2: the CANONICAL FAIRNESS DIGEST. Order-independent sha256 over SORTED event tuples,
# the full 64 hex characters, never a prefix taken in iteration order. Coverage:
#   device_register, session_start, session_end, history_append, recall_question,
#   and monitor_offer in PULL mode (B) or monitor_frame in PUSH mode (A).
# In pull mode the frames are EXCLUDED, because which frames exist depends on the arm's own
# pulls and so cannot be a fairness invariant (D69, D96).
FAIRNESS_KINDS_COMMON = ("device_register", "session_start", "session_end", "history_append",
                         "recall_question")


def fairness_kinds(upload_mode: str) -> tuple:
    return FAIRNESS_KINDS_COMMON + (("monitor_offer",) if upload_mode == "B"
                                    else ("monitor_frame",))


def _fairness_row(e: Dict[str, Any]) -> tuple:
    """One canonical row per covered event.

    THE SHAPE IS THE FLEET'S, which D96 makes canonical: `fleet/trace.py::_digest_tuple` emits
    `(device_id, wire_kind, t, key, extra, deadline)` with times to six decimals, and this
    function reproduces it field for field so the two sides' digests are comparable. The wire
    events carry the time under its own name, and the mapping onto the fleet's single `t` is:
    `start_t` for a registration, `t` for a session boundary, `t_arrive` for a history batch,
    `t_ask` for a question and `t_capture` for a monitoring instant.
    """
    k = e["kind"]
    dev = str(e["device_id"])
    if k == "device_register":
        return (dev, "device_register", "%.6f" % float(e["start_t"]), "", "", "")
    if k in ("session_start", "session_end"):
        return (dev, k, "%.6f" % float(e["t"]), str(e["session_id"]), "", "")
    if k == "history_append":
        return (dev, "history_append", "%.6f" % float(e["t_arrive"]), str(e["batch_id"]),
                str(int(e["est_tokens"])), "")
    if k == "recall_question":
        return (dev, "recall_question", "%.6f" % float(e["t_ask"]),
                str(e["opportunity_id"]), str(e["session_id"]),
                "%.6f" % float(e["deadline_s"]))
    if k in ("monitor_offer", "monitor_frame"):
        return (dev, k, "%.6f" % float(e["t_capture"]), str(e["opportunity_id"]), "",
                "%.6f" % float(e["deadline_s"]))
    raise KeyError("kind %r is not covered by the fairness digest" % k)


def fairness_digest(events: List[Dict[str, Any]], upload_mode: str = "A") -> str:
    kinds = set(fairness_kinds(upload_mode))
    rows = sorted(_fairness_row(e) for e in events if e["kind"] in kinds)
    h = hashlib.sha256()
    for row in rows:
        h.update(("|".join(row) + "\n").encode())
    return h.hexdigest()


def live1_trace_digest(events: List[Dict[str, Any]]) -> str:
    """The StudyLIVE1-port digest, kept ONLY under this name (D96 part 2)."""
    h = hashlib.sha256()
    for e in events:
        if e["kind"] in ("monitor_offer", "monitor_frame"):
            h.update(repr((e["kind"], e["device_id"], e["opportunity_id"],
                           round(float(e["t_capture"]), 4))).encode())
        elif e["kind"] == "recall_question":
            h.update(repr(("recall", e["device_id"], e["opportunity_id"],
                           round(float(e["t_ask"]), 4))).encode())
        elif e["kind"] == "device_register":
            h.update(repr(("reg", e["device_id"], e["type"],
                           round(float(e["start_t"]), 4))).encode())
    return h.hexdigest()[:32]


def upload_s(nbytes: int, uplink_mbps: float = UPLINK_MBPS, rtt_ms: float = RTT_MS) -> float:
    return nbytes * 8.0 / (uplink_mbps * 1e6) + rtt_ms / 2000.0


def synthetic(*, n_dashcam: int = 2, n_robot: int = 2, duration_s: float = 60.0,
              seed: int = 1, upload_mode: str = "A", frames_dir: Optional[Path] = None,
              questions_per_session: int = 3, session_s: float = 430.0,
              frame_bytes: int = int(E10A_NEXAR_Q90_MEDIAN_B)) -> Dict[str, Any]:
    """A SYNTHETIC trace. Labelled as such everywhere it is used."""
    rng = random.Random(seed)
    ev: List[Dict[str, Any]] = []
    frames_by_instant: Dict[str, str] = {}
    frames_dir = Path(frames_dir) if frames_dir else None
    written: List[str] = []

    def frame_file(name: str, nbytes: int) -> str:
        if frames_dir is None:
            return name
        frames_dir.mkdir(parents=True, exist_ok=True)
        p = frames_dir / name
        if not p.exists():
            r = random.Random(hashlib_int(name))
            p.write_bytes(bytes(r.randrange(256) for _ in range(max(nbytes, 1))))
            written.append(str(p))
        return str(p)

    for i in range(n_dashcam):
        did = f"dash{i:03d}"
        start = round(rng.uniform(0.0, NEXAR_INSTANT_CADENCE_S), 4)
        ev.append(SC.make("device_register", device_id=did, type="dashcam",
                          uplink_mbps=UPLINK_MBPS, rtt_ms=RTT_MS, start_t=start))
        k = 0
        t = start
        while t <= duration_s:
            iid = f"{did}/i{k:05d}"
            # D96: the TRACE GENERATOR assigns the opportunity_id, unique within the run. The
            # coordinator only ever copies it.
            opp = f"{did}|i{k:05d}"
            ref = frame_file(f"{did}_i{k:05d}.bin", frame_bytes // 200)
            frames_by_instant[opp] = ref
            if upload_mode == "B":
                ev.append(SC.make("monitor_offer", device_id=did, opportunity_id=opp,
                                  instant_id=iid, t_capture=round(t, 4),
                                  deadline_s=DASHCAM_L_S, frame_bytes=frame_bytes))
            else:
                ev.append(SC.make("monitor_frame", device_id=did, opportunity_id=opp,
                                  instant_id=iid, t_capture=round(t, 4),
                                  t_arrive=round(t + upload_s(frame_bytes), 4),
                                  deadline_s=DASHCAM_L_S, frame_ref=ref,
                                  frame_bytes=frame_bytes))
            k += 1
            t = round(start + k * NEXAR_INSTANT_CADENCE_S, 4)

    for j in range(n_robot):
        did = f"rob{j:03d}"
        offset = round(rng.uniform(0.0, session_s * 0.5), 3)       # D83 staggered start
        ev.append(SC.make("device_register", device_id=did, type="robot",
                          uplink_mbps=UPLINK_MBPS, rtt_ms=RTT_MS, start_t=0.0))
        play, t0 = 0, 0.0
        while t0 <= duration_s:
            sid = f"{did}/s{play}/play{play}"
            ev.append(SC.make("session_start", device_id=did, session_id=sid, t=round(t0, 4)))
            n_batches = max(1, int((min(duration_s, t0 + session_s - offset) - t0)
                                   // BATCH_PERIOD_S) + 1)
            frames_so_far = 0
            for b in range(n_batches):
                tb = round(t0 + (b + 1) * BATCH_PERIOD_S, 4)
                if tb > duration_s + BATCH_PERIOD_S:
                    break
                n = int(BATCH_PERIOD_S / D2_STRIDE_S)
                refs = [frame_file(f"{did}_s{play}_f{frames_so_far + m:05d}.bin", 2_000)
                        for m in range(n)]
                frames_so_far += n
                ev.append(SC.make("history_append", device_id=did, session_id=sid,
                                  batch_id=f"{sid}/b{b}", t_arrive=tb, frame_refs=refs,
                                  est_tokens=D2_HEADER_TOK + frames_so_far * D2_TOK_PER_IMG))
            for qi in range(questions_per_session):
                tq = round(t0 + BATCH_PERIOD_S * 1.5 + qi * BATCH_PERIOD_S, 4)
                if tq > duration_s:
                    break
                ev.append(SC.make("recall_question", device_id=did,
                                  opportunity_id=f"{sid}|q{qi}", session_id=sid,
                                  question_id=f"{sid}/q{qi}", t_ask=tq,
                                  t_arrive=round(tq + upload_s(2_000), 4),
                                  deadline_s=ROBOT_L_S,
                                  question="SYNTHETIC question %d" % qi,
                                  options=["A", "B", "C", "D"]))
            t_end = round(min(t0 + session_s - offset, duration_s + 1.0), 4)
            ev.append(SC.make("session_end", device_id=did, session_id=sid, t=t_end))
            play += 1
            t0 = t_end
            offset = 0.0

    ev.sort(key=lambda e: (_sched(e), e["kind"]))
    return dict(label="SYNTHETIC", events=ev,
                fairness_digest=fairness_digest(ev, upload_mode),
                live1_trace_digest=live1_trace_digest(ev), seed=seed,
                frames_by_instant=frames_by_instant,
                upload_mode=upload_mode, duration_s=duration_s,
                n_dashcam=n_dashcam, n_robot=n_robot, frames_dir=str(frames_dir or ""),
                frame_files=len(written), constants=_SOURCES,
                note=("SYNTHETIC TEST FIXTURE. The frame files are PLACEHOLDER BYTES, not "
                      "JPEGs, and no clip, session or question in this trace is real. Nothing "
                      "produced from it is a measurement."))


def hashlib_int(s: str) -> int:
    return int(hashlib.sha256(s.encode()).hexdigest()[:8], 16)


def _sched(ev: Dict[str, Any]) -> float:
    for k in ("t_arrive", "t_capture", "start_t", "t", "t_ask"):
        if ev.get(k) is not None:
            return float(ev[k])
    return 0.0


def load(path: Any) -> Dict[str, Any]:
    """Read a fleet trace JSONL.

    Two shapes are accepted: a file whose first record is a `_header`, and the fleet's own
    `trace.jsonl` + sibling `trace_meta.json` (StudyLIVE2-fleet `fleet/trace.py::write_trace`).
    A trace from the fleet is labelled FLEET, so `require_fake_server` lets it run against a
    real server while a SYNTHETIC one is refused. Every record is parsed through `schema.parse`,
    so an off-schema trace fails here rather than inside the loop.
    """
    p = Path(path)
    recs = SC.read_jsonl(p)
    head = [r for r in recs if r.get("kind") == "_header"]
    ev = [r for r in recs if r.get("kind") != "_header"]
    for r in ev:
        SC.parse(r)
    meta_path = p.parent / "trace_meta.json"
    meta = {}
    if not head and meta_path.exists():
        import json as _json
        meta = _json.loads(meta_path.read_text())
    label = (head[0].get("label") if head else None) or ("FLEET" if meta else "UNLABELLED")
    frames = {e["opportunity_id"]: e.get("frame_ref") for e in ev
              if e["kind"] in ("monitor_frame", "monitor_offer") and e.get("frame_ref")}
    mode = (head[0].get("upload_mode") if head else meta.get("mode")) or "A"
    return dict(label=label, events=sorted(ev, key=lambda e: (_sched(e), e["kind"])),
                fairness_digest=fairness_digest(ev, mode),
                live1_trace_digest=live1_trace_digest(ev),
                seed=(head[0].get("seed") if head else meta.get("seed")),
                upload_mode=mode,
                fleet_opportunity_digest=meta.get("opportunity_digest"),
                frames_by_instant=frames, meta=meta or None, path=str(p))


def write(trace: Dict[str, Any], path: Any) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    head = dict(kind="_header", label=trace["label"], seed=trace.get("seed"),
                upload_mode=trace.get("upload_mode"),
                fairness_digest=trace["fairness_digest"],
                live1_trace_digest=trace.get("live1_trace_digest"),
                note=trace.get("note"))
    SC.write_jsonl(p, [head] + trace["events"])
    return p


def require_fake_server(trace: Dict[str, Any], server_kind: str) -> None:
    if trace.get("label") == "SYNTHETIC" and server_kind != "fake":
        raise SyntheticTraceRefused(
            "a SYNTHETIC trace carries placeholder frame bytes and invented questions; it may "
            "be run against the CPU stub only, never a model server (%r)" % server_kind)


def pull_responder(trace_frames: Dict[str, Any], frame_bytes_default: int = 60_000):
    """Mode B (D69): the frame a pull produces, with the pull message and the upload charged.

    Delivered delay for the pulled path therefore carries, in order: the pull message (RTT / 2),
    the device's upload of the frame, and RTT / 2 on the way in, which is what `upload_s`
    already includes.
    """
    def respond(o, t: float) -> Dict[str, Any]:
        nb = int(o.frame_bytes or frame_bytes_default)
        ref = trace_frames.get(o.opp_id) or o.opp_id
        return SC.make("monitor_frame", device_id=o.device_id, opportunity_id=o.opp_id,
                       instant_id=o.instant_id or o.opp_id, t_capture=o.t_event,
                       t_arrive=round(t + RTT_MS / 2000.0 + upload_s(nb), 4),
                       deadline_s=o.deadline_s, frame_ref=ref, frame_bytes=nb)
    return respond
