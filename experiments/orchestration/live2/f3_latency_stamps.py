#!/usr/bin/env python3
"""F3 LATENCY BREAKDOWN: one stamped row per request, EVERY STAMP MARKED EMULATED OR MEASURED.

D214 figure F3 is a latency CDF. The whole point of this file is that an F3 built on this project's
harness MIXES TWO REGISTERS, and a CDF that mixes them without saying so invites a reader to treat
an emulated serialisation as an observation:

  EMULATED   the frame upload and the answer's return to the device. Both are the harness's own
             link arithmetic (`fleet/links.py`, D75): bytes * 8 / uplink + RTT / 2 on an uplink
             shared FIFO per device. NO PACKET IS SENT. A 63,898 B dashcam JPEG "takes" 0.0376 s
             because that is what the arithmetic says, not because anything was measured.
  MEASURED   engine submit, first token and done. These come off the REAL server: `sent_s` is the
             run clock read AS THE REQUEST GOES ON THE WIRE (`asyncbackend.py`, D107 (2)), and
             `ttft_s` / `total_s` are the streaming client's own wall-clock readings.
  DERIVED    a stamp computed from stamps of both registers, so it is neither. The answer's return
             to the device is the clearest one: a MEASURED `t_done` plus an EMULATED delivery term.
             It is marked DERIVED and its two parts are named, rather than being called measured
             because its larger part is.

THE REGISTER IS CARRIED IN THE EMITTED RECORD, not only in a report (D214 item 3's rule applied to
item 1): every stamp in `f3_latency_stamps.jsonl` is an object with `t`, `register` and `source`,
where `source` names the file and the code site the number came from.

EVERY STAMP IS REUSED, NONE IS A SECOND SOURCE OF TRUTH (D107). This file adds no stamp to the
coordinator and does not touch `coordinator.py`. It JOINS logs that already exist:

  stamp                     reused from                                      register
  frame upload start/end    `uplink_transfers.jsonl.gz` (this run's dump of  EMULATED
                            `links.UplinkQueue.log`: t_offer, t_start,
                            t_arrive, queue_s per transfer)
  coordinator receive       the same transfer's `t_arrive`, which is the     EMULATED
                            instant `emulator.py` pushes frame_arrived /
                            question_arrived and calls `coord.on_event`
                            (`:386-391`, `:418-419`); for a monitor it is
                            also `outcomes.jsonl` `t_frame_arrive`
  coordinator release       `decision.jsonl` `t`, the epoch's NOMINAL        MEASURED
                            instant, which is exactly `sub.meta.nominal_t`   (run clock)
                            at `coordinator.py:1524`. D107 (2): the request
                            is stamped at the wire and the nominal instant
                            is carried in meta, so the policy's own decision
                            time is charged as SUBMIT DELAY. Hold time is
                            release - receive; submit delay is submit -
                            release, and they are reported separately
  engine submit             `request.jsonl` `t_submit` = `sub.sent_s`, the   MEASURED
                            wire stamp (`asyncbackend.py:250-258`)
  first token               `request.jsonl` `t_first_token` =                MEASURED
                            sent_s + ttft_s * speed. D107 (1): THE ANSWER
                            IS FORWARDED AT THE FIRST CONTENT TOKEN, so this
                            is the instant the answer left the cloud, not an
                            intermediate
  done                      `request.jsonl` `t_done` = sent_s + total_s *    MEASURED
                            speed, the stream end
  answer return to device   `outcomes.jsonl` `t_delivered`, which the        DERIVED
                            emulator schedules as the forwarded answer's
                            `t_done` + `links.deliver_s(RTT/2 + payload /
                            downlink)` (`emulator.py:349-353`)

TWO THINGS A READER MUST NOT MISREAD, SAID HERE RATHER THAN IN A FOOTNOTE.

  1. `speed`. `t_first_token` and `t_done` are `sent_s + ttft_s * speed`. On a real-server cell
     `speed` is 1.0 and they are the measured instants; if a cell ran with any other speed the
     stamps are SCALED measurements and this file records `speed_note` rather than silently
     reporting them as measured. The value is not recoverable from the logs, so it is taken from
     `run_meta.json` where present and reported as unknown where not.
  2. The answer-return stamp in `outcomes.jsonl` is keyed on the OPPORTUNITY, not the request, and
     under D107 (1) the forwarded answer is the FIRST-CONTENT-TOKEN one. So where several requests
     share an opportunity, `t_delivered` belongs to whichever answer was forwarded; the row records
     `n_requests_on_this_opportunity` so a reader can see when that is more than one instead of
     assuming a one-to-one join.

ABSENCES ARE COUNTED, NEVER ASSUMED AWAY. A stamp that could not be joined is emitted as
`{"t": null, "register": ..., "source": ..., "absent_reason": ...}` and every absence is counted in
`f3_stamp_registers.json`, so a CDF built from the rows can state its own coverage.

USAGE
  as a library, from the live runner, after the run:
      import f3_latency_stamps as F3
      F3.dump_uplink_transfers(em, rdir)            # the EMULATED upload stamps
      F3.build(rdir, tdir)                          # the joined rows + the register table
  as a CLI on an existing cell directory:
      python f3_latency_stamps.py --run-dir DIR [--trace-dir DIR]

LIVE CELLS ONLY, as D214 item 1 asks. A dry cell has no server, so `request.jsonl` carries the
stub's own service times and nothing in it is MEASURED; `build` records `live=false` in that case
and the rows must not go into an F3 CDF. The test is the presence of a real `http_status`.
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

TRANSFERS = "uplink_transfers.jsonl.gz"
ROWS = "f3_latency_stamps.jsonl"
REGISTERS = "f3_stamp_registers.json"

EMULATED = "EMULATED"
MEASURED = "MEASURED"
DERIVED = "DERIVED"

_EMU_NOTE = ("the harness's own link arithmetic (fleet/links.py, D75: bytes * 8 / uplink + RTT / 2 "
             "on a per-device FIFO uplink). NO PACKET WAS SENT.")


# ------------------------------------------------------------------ the EMULATED upload stamps

def dump_uplink_transfers(em: Any, out_dir: Path) -> Dict[str, Any]:
    """Write every uplink transfer the emulator performed, with its three instants.

    `links.UplinkQueue` ALREADY records t_offer, t_start, t_arrive and queue_s per transfer and
    keeps them in `self.log`; `run_meta.json` carries only `stats()` over them (n, busy_s and three
    queue quantiles). So the per-frame upload start and end that F3 needs exist on the object and
    have simply never been written out. This dumps them. It runs AFTER `em.run()` has returned and
    reads only; it is why F3 needs no change to the emulator.
    """
    out_dir = Path(out_dir)
    n = 0
    by_kind: Dict[str, int] = {}
    with gzip.open(out_dir / TRANSFERS, "wt") as fh:
        for dev in sorted(getattr(em, "queues", {}) or {}):
            q = em.queues[dev]
            spec = getattr(q, "spec", None)
            up = getattr(spec, "uplink_mbps", None)
            rtt = getattr(spec, "rtt_ms", None)
            for tr in getattr(q, "log", []) or []:
                d = tr.as_dict() if hasattr(tr, "as_dict") else dict(tr)
                d["device_id"] = dev
                d["uplink_mbps_applied"] = up
                d["rtt_ms_applied"] = rtt
                d["register"] = EMULATED
                n += 1
                by_kind[d.get("kind", "?")] = by_kind.get(d.get("kind", "?"), 0) + 1
                fh.write(json.dumps(d, sort_keys=True, separators=(",", ":")) + "\n")
    return {"file": TRANSFERS, "n_transfers": n, "by_kind": dict(sorted(by_kind.items())),
            "register": EMULATED, "register_note": _EMU_NOTE,
            "source": "links.UplinkQueue.log, read off the emulator after the run"}


# ------------------------------------------------------------------------------------ the join

def _jsonl(p: Path) -> List[Dict[str, Any]]:
    if not p.exists():
        return []
    op = gzip.open if p.name.endswith(".gz") else open
    out = []
    with op(p, "rt") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _stamp(t: Optional[float], register: str, source: str,
           absent_reason: Optional[str] = None, **extra: Any) -> Dict[str, Any]:
    d: Dict[str, Any] = {"t": (None if t is None else round(float(t), 6)),
                         "register": register, "source": source}
    if t is None:
        d["absent_reason"] = absent_reason or "not present in the joined logs"
    d.update(extra)
    return d


def _gap(a: Dict[str, Any], b: Dict[str, Any]) -> Optional[float]:
    """b - a in seconds, or None if either end is absent. DERIVED wherever the ends differ."""
    if a.get("t") is None or b.get("t") is None:
        return None
    return round(float(b["t"]) - float(a["t"]), 6)


def build(run_dir: Path, trace_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Join the existing logs into `f3_latency_stamps.jsonl` and write the register table."""
    run_dir = Path(run_dir)
    reqs = _jsonl(run_dir / "request.jsonl")
    decs = _jsonl(run_dir / "decision.jsonl")
    outs = _jsonl(run_dir / "outcomes.jsonl")
    trs = _jsonl(run_dir / TRANSFERS)
    meta = {}
    if (run_dir / "run_meta.json").exists():
        meta = json.loads((run_dir / "run_meta.json").read_text())

    dec_t = {d.get("decision_id"): d.get("t") for d in decs if d.get("decision_id")}
    dec_lat = {d.get("decision_id"): d.get("decision_latency_ms") for d in decs
               if d.get("decision_id")}
    out_by_opp = {o.get("opportunity_id"): o for o in outs if o.get("opportunity_id")}
    tr_by_ref: Dict[str, List[Dict[str, Any]]] = {}
    for t in trs:
        tr_by_ref.setdefault(str(t.get("ref")), []).append(t)

    # trace-side frame refs, so a transfer can name the FRAME it carried and not only its ref
    frame_refs: Dict[str, List[str]] = {}
    batch_session: Dict[str, Optional[str]] = {}
    if trace_dir is not None:
        for r in _jsonl(Path(trace_dir) / "trace.jsonl"):
            k = r.get("kind")
            if k in ("monitor_frame", "monitor_offer"):
                ref = str(r.get("opportunity_id") or r.get("instant_id") or "")
                fr = list(r.get("frame_refs") or ([r["frame_ref"]] if r.get("frame_ref") else []))
                if ref:
                    frame_refs[ref] = fr
            elif k == "history_batch":
                ref = str(r.get("batch_id") or "")
                if ref:
                    frame_refs[ref] = list(r.get("frame_refs") or [])
                    batch_session[ref] = r.get("session_id")

    per_opp: Dict[str, int] = {}
    for r in reqs:
        o = r.get("opportunity_id")
        if o:
            per_opp[o] = per_opp.get(o, 0) + 1

    live = any(isinstance(r.get("http_status"), int) for r in reqs)
    speed = meta.get("speed")
    absent: Dict[str, int] = {}
    n = 0
    with open(run_dir / ROWS, "w") as fh:
        for r in reqs:
            rid = r.get("request_id")
            did = r.get("decision_id")
            opp = r.get("opportunity_id")
            o = out_by_opp.get(opp) or {}

            # --- EMULATED: the uploads whose bytes this request's prompt refers to
            ups: List[Dict[str, Any]] = []
            for t in tr_by_ref.get(str(opp), []):
                ups.append(_upload_row(t, frame_refs))
            # `SC.RequestRecord` carries NO `kind` field (schema.py:364-381), so the request's kind
            # comes from its OPPORTUNITY. Reading `r["kind"]` here silently made every row a
            # non-recall and dropped every history upload from the join.
            kind = r.get("kind") or o.get("kind")
            if kind == "recall" and r.get("session_id"):
                sid = r["session_id"]
                for ref, rows in tr_by_ref.items():
                    if batch_session.get(ref) != sid:
                        continue
                    for t in rows:
                        if (t.get("t_arrive") is not None and r.get("t_submit") is not None
                                and float(t["t_arrive"]) <= float(r["t_submit"]) + 1e-9):
                            ups.append(_upload_row(t, frame_refs))
            ups.sort(key=lambda x: (x.get("t_upload_start", {}).get("t") is None,
                                    x.get("t_upload_start", {}).get("t") or 0.0))

            recv_t = o.get("t_frame_arrive")
            recv_src = "outcomes.jsonl t_frame_arrive (emulator.py:386 / :406)"
            if recv_t is None and ups:
                recv_t = ups[-1].get("t_upload_end", {}).get("t")
                recv_src = (TRANSFERS + " t_arrive of the last upload this request refers to "
                            "(emulator.py pushes frame_arrived / question_arrived at that instant "
                            "and calls coord.on_event)")
            rel_t = dec_t.get(did)

            s_recv = _stamp(recv_t, EMULATED, recv_src,
                            absent_reason=("no upload and no t_frame_arrive for this request's "
                                           "opportunity; a recall question's own 1,200 B text "
                                           "upload is keyed on the opportunity and is present, so "
                                           "an absence here means the opportunity is not in "
                                           "outcomes.jsonl"),
                            register_note=_EMU_NOTE)
            s_rel = _stamp(rel_t, MEASURED,
                           "decision.jsonl t for decision_id %r, which is sub.meta.nominal_t "
                           "(coordinator.py:1524) -- the epoch's nominal instant, D107 (2)" % did,
                           absent_reason=("this request carries no decision_id, or no decision row "
                                          "has it; coordinator release is then not recoverable"),
                           register_note=("the run clock read in the coordinator process; the "
                                          "epoch instant itself, NOT the wire instant"))
            s_sub = _stamp(r.get("t_submit"), MEASURED,
                           "request.jsonl t_submit = sub.sent_s, stamped AT THE WIRE "
                           "(asyncbackend.py:250-258, D107 (2))")
            s_ft = _stamp(r.get("t_first_token"), MEASURED,
                          "request.jsonl t_first_token = sent_s + ttft_s * speed; D107 (1): the "
                          "answer is forwarded AT THE FIRST CONTENT TOKEN")
            s_done = _stamp(r.get("t_done"), MEASURED,
                            "request.jsonl t_done = sent_s + total_s * speed, the stream end")
            s_ret = _stamp(o.get("t_delivered"), DERIVED,
                           "outcomes.jsonl t_delivered = the forwarded answer's t_done + "
                           "links.deliver_s(RTT/2 + payload / downlink) (emulator.py:349-353)",
                           absent_reason=("this opportunity was never delivered: no cloud answer "
                                          "reached the device"),
                           register_note=("MIXED: a MEASURED cloud instant plus an EMULATED "
                                          "downlink term. " + _EMU_NOTE),
                           measured_part="the cloud answer's own instant",
                           emulated_part="RTT/2 + answer_payload_bytes / downlink_mbps")

            row = {
                "request_id": rid, "decision_id": did, "device_id": r.get("device_id"),
                "kind": kind, "kind_source": "outcomes.jsonl (RequestRecord carries no kind)",
                "session_id": r.get("session_id"),
                "opportunity_id": opp,
                "n_requests_on_this_opportunity": per_opp.get(opp),
                "deadline_s": o.get("deadline_s"),
                "t_opportunity": _stamp(o.get("t_opportunity"), EMULATED,
                                        "outcomes.jsonl t_opportunity, the trace's capture / ask "
                                        "instant on the run clock"),
                "frame_uploads": ups,
                "t_coordinator_receive": s_recv,
                "t_coordinator_release": s_rel,
                "t_engine_submit": s_sub,
                "t_first_token": s_ft,
                "t_done": s_done,
                "t_answer_return_to_device": s_ret,
                "derived": {
                    "_register": DERIVED,
                    "hold_s": _gap(s_recv, s_rel),
                    "hold_s_note": ("coordinator release - coordinator receive. Spans an EMULATED "
                                    "end and a MEASURED end, so it is DERIVED and not a measured "
                                    "queueing time."),
                    "submit_delay_s": _gap(s_rel, s_sub),
                    "submit_delay_s_note": ("engine submit - coordinator release: D107 (2)'s "
                                            "submit delay, the policy's own decision time charged "
                                            "to the request. Both ends MEASURED."),
                    "ttft_s": _gap(s_sub, s_ft),
                    "service_s": _gap(s_sub, s_done),
                    # D107 (1): THE ANSWER IS FORWARDED AT THE FIRST CONTENT TOKEN, so the
                    # emulated downlink term runs from `t_first_token`, NOT from the stream end.
                    # Differencing against `t_done` gives a NEGATIVE "downlink time" on every row
                    # whose stream outlived its first token, which is most of them, and a negative
                    # latency component in an F3 CDF would be read as an instrumentation fault
                    # rather than as the forwarding rule it actually is.
                    "forward_to_device_s": _gap(s_ft, s_ret),
                    "forward_to_device_s_note": ("answer return - first token: the EMULATED "
                                                 "downlink term, RTT/2 + payload / downlink. D107 "
                                                 "(1) forwards at the first content token."),
                    "done_to_return_s": _gap(s_done, s_ret),
                    "done_to_return_s_note": ("answer return - stream end. NEGATIVE wherever the "
                                              "stream outlived its first content token, which is "
                                              "D107 (1) working, not a fault. Reported for the "
                                              "register; it is not a latency component."),
                    "end_to_end_s": _gap(row_first(ups, s_recv), s_ret),
                    "end_to_end_note": ("first upload offer (or coordinator receive where no "
                                        "upload was joined) to the answer's return. MIXES "
                                        "REGISTERS end to end: an EMULATED start, a MEASURED "
                                        "middle, a DERIVED end."),
                },
                "decision_latency_ms": dec_lat.get(did),
                "prompt_tokens": r.get("prompt_tokens"), "cached_tokens": r.get("cached_tokens"),
                "cache_path": r.get("cache_path"), "http_status": r.get("http_status"),
            }
            for k in ("t_coordinator_receive", "t_coordinator_release", "t_engine_submit",
                      "t_first_token", "t_done", "t_answer_return_to_device"):
                if row[k].get("t") is None:
                    absent[k] = absent.get(k, 0) + 1
            if not ups:
                absent["frame_uploads"] = absent.get("frame_uploads", 0) + 1
            n += 1
            fh.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    reg = {
        "_what": ("the register of every stamp in " + ROWS + ", so an F3 CDF can state which of "
                  "its axis is observed and which is the harness's arithmetic. The register is "
                  "ALSO on every stamp in every row; this file is the summary, not the source."),
        "live_cell": live,
        "live_cell_test": ("any request.jsonl row carries an integer http_status. A dry cell's "
                           "rows carry none, nothing in them is MEASURED, and they must not go "
                           "into an F3 CDF."),
        "speed": speed,
        "speed_note": ("t_first_token and t_done are sent_s + ttft_s|total_s * speed. speed 1.0 "
                       "means they are the measured instants; any other value makes them SCALED "
                       "measurements. Read from run_meta.json; null means it was not recorded "
                       "there and the register of those two stamps is unverified."),
        "n_rows": n,
        "n_transfers_joined": len(trs),
        "absent_stamps": dict(sorted(absent.items())),
        "registers": {
            "t_opportunity": EMULATED,
            "frame_uploads.t_upload_offer": EMULATED,
            "frame_uploads.t_upload_start": EMULATED,
            "frame_uploads.t_upload_end": EMULATED,
            "t_coordinator_receive": EMULATED,
            "t_coordinator_release": MEASURED,
            "t_engine_submit": MEASURED,
            "t_first_token": MEASURED,
            "t_done": MEASURED,
            "t_answer_return_to_device": DERIVED,
        },
        "emulated_note": _EMU_NOTE,
        "measured_note": ("off the real server through the streaming client: sent_s is the run "
                          "clock AS THE REQUEST GOES ON THE WIRE (D107 (2)) and ttft_s / total_s "
                          "are the client's own wall-clock readings."),
        "derived_note": ("a stamp computed from stamps of both registers. It is NOT measured "
                         "because its larger part is."),
        "reused_not_added": ("every stamp above already existed in decision.jsonl, request.jsonl "
                             "or outcomes.jsonl, or on links.UplinkQueue.log. This file adds NO "
                             "stamp to coordinator.py and creates no second source of truth for "
                             "any instant (D107)."),
    }
    (run_dir / REGISTERS).write_text(json.dumps(reg, indent=2, sort_keys=True) + "\n")
    return reg


def row_first(ups: List[Dict[str, Any]], fallback: Dict[str, Any]) -> Dict[str, Any]:
    """The earliest upload offer, or the coordinator-receive stamp where no upload was joined."""
    for u in ups:
        if u.get("t_upload_offer", {}).get("t") is not None:
            return u["t_upload_offer"]
    return fallback


def _upload_row(t: Dict[str, Any], frame_refs: Dict[str, List[str]]) -> Dict[str, Any]:
    ref = str(t.get("ref"))
    return {
        "kind": t.get("kind"), "ref": ref, "bytes": t.get("bytes"),
        "frame_refs": frame_refs.get(ref),
        "frame_refs_source": (
            "trace.jsonl frame_refs for this ref" if ref in frame_refs else
            ("NOT A FRAME: a recall question's own 1,200 B of text (emulator.py QUESTION_TEXT_B), "
             "which occupies the same uplink and is stamped the same way"
             if t.get("kind") == "recall_question" else
             "NOT RESOLVED: no trace record carries this ref. Pass --trace-dir if it was omitted")),
        "uplink_mbps_applied": t.get("uplink_mbps_applied"),
        "rtt_ms_applied": t.get("rtt_ms_applied"),
        "t_upload_offer": _stamp(t.get("t_offer"), EMULATED,
                                 TRANSFERS + " t_offer: when the device wanted to send"),
        "t_upload_start": _stamp(t.get("t_start"), EMULATED,
                                 TRANSFERS + " t_start = max(t_offer, uplink free_at): THE UPLOAD "
                                 "START, after the per-device FIFO"),
        "t_upload_end": _stamp(t.get("t_arrive"), EMULATED,
                               TRANSFERS + " t_arrive = t_start + bytes * 8 / uplink + RTT / 2: "
                               "THE UPLOAD END, when the last byte has landed"),
        "queue_s": t.get("queue_s"),
        "register": EMULATED, "register_note": _EMU_NOTE,
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--trace-dir", default=None,
                    help="the cell's trace directory, so an upload can name the FRAME it carried "
                         "and not only its ref. Optional: without it frame_refs is null and the "
                         "row says why.")
    a = ap.parse_args(list(argv) if argv is not None else None)
    rd = Path(a.run_dir)
    td = Path(a.trace_dir) if a.trace_dir else None
    if td is None:
        cj = rd / "cell.json"
        if cj.exists():
            td = Path(json.loads(cj.read_text()).get("trace_dir") or ".")
            if not (td / "trace.jsonl").exists():
                td = None
    reg = build(rd, td)
    print(json.dumps(reg, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
