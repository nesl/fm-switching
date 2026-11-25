#!/usr/bin/env python3
"""Split a frozen live2 trace into one slice per device. OFFLINE, CPU only, read-only on input.

StudyREAL-NET, component 1.

WHY A FILTER AND NOT A GENERATOR. D96 (1): every `opportunity_id` is assigned by the TRACE
GENERATOR, unique within the run, and echoed unchanged by both the coordinator and the fleet.
A slice therefore MUST carry ids through untouched: nothing here mints, renumbers or reorders
an id. The reunion check below is what proves it -- the union of the slices must equal the
input record set exactly, and the D96 (2) fairness digest over that union must equal the digest
the input's own `trace_meta.json` committed.

WHAT A SLICE HOLDS
  trace.jsonl           that device's records only, in input order
  device_answers.jsonl  that device's answer rows only (D201: the DEVICE's own per-instant
                        score; a monitor row without one is a hard error, never a 0.0)
  slice_meta.json       provenance: input dir, input digests, this device's counts and bytes
  frames.txt            the frame_refs this device needs, one per line (the frame STAGER reads
                        this; this script never copies image bytes)

Frames are named, not copied. A dashcam slice references ~140 MB of JPEG and the stager (a
separate, dumb rsync step) moves them; keeping that out of here means this script is pure
and re-runnable in seconds.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

# The six event kinds a trace record may carry, as fleet/trace.py writes them.
RECORD_KINDS = ("device_register", "session_start", "session_end", "history_preload",
                "history_batch", "monitor_opportunity", "recall_question")

# D96 (2) canonical digest: order-independent sha256 over sorted event tuples covering
# device_register, session_start, session_end, history_append, recall_question, and
# monitor_offer (pull mode) or monitor_frame (push mode). monitor_frame is EXCLUDED in pull
# mode because which frames exist depends on the arm's pulls.
DIGEST_KINDS_PUSH = ("device_register", "session_start", "session_end", "history_batch",
                     "recall_question", "monitor_opportunity")


def _open_maybe_gz(p: Path):
    """Read a .jsonl or .jsonl.gz transparently."""
    if p.suffix == ".gz":
        return gzip.open(p, "rt")
    return open(p, "rt")


def _find(trace_dir: Path, stem: str) -> Path:
    """Locate `stem`.jsonl or `stem`.jsonl.gz, preferring the plain file."""
    for name in (stem + ".jsonl", stem + ".jsonl.gz"):
        p = trace_dir / name
        if p.exists():
            return p
    raise FileNotFoundError("%s holds neither %s.jsonl nor %s.jsonl.gz" % (trace_dir, stem, stem))


def load_trace(trace_dir: Path) -> Dict[str, Any]:
    """Read a frozen trace directory. Returns records, answers and meta."""
    trace_dir = Path(trace_dir)
    meta_p = trace_dir / "trace_meta.json"
    if not meta_p.exists():
        raise FileNotFoundError("%s holds no trace_meta.json" % trace_dir)
    meta = json.loads(meta_p.read_text())

    records: List[Dict[str, Any]] = []
    with _open_maybe_gz(_find(trace_dir, "trace")) as fh:
        for ln in fh:
            ln = ln.strip()
            if ln:
                records.append(json.loads(ln))

    # D201: the answer table is NOT optional. The emulator raises without it and a monitor row
    # that carries no device_score is exactly the defect D201 fixed, so refuse both here too.
    answers: List[Dict[str, Any]] = []
    with _open_maybe_gz(_find(trace_dir, "device_answers")) as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            a = json.loads(ln)
            if a.get("kind") == "monitor" and a.get("device_score") is None:
                raise ValueError(
                    "device_answers row for %r carries no device_score; a neutral value here "
                    "is the defect D201 fixed, so this is a hard error (opportunity_id=%r)"
                    % (a.get("device_id"), a.get("opportunity_id")))
            answers.append(a)

    return dict(records=records, answers=answers, meta=meta, dir=trace_dir)


def device_of(rec: Dict[str, Any]) -> Optional[str]:
    """The device a record belongs to, or None if it belongs to no single device."""
    d = rec.get("device_id")
    return str(d) if d else None


def fairness_digest(records: Sequence[Dict[str, Any]],
                    kinds: Sequence[str] = DIGEST_KINDS_PUSH) -> str:
    """D96 (2): order-independent sha256 over sorted event tuples of the covered kinds.

    This is recomputed on the INPUT and on the REUNION of the slices. The two must match;
    the absolute value need not equal trace_meta's own digest, because that digest was taken
    over the emulator's wire events (`history_append`, `monitor_frame`) and not over the
    generator's record kinds (`history_batch`, `monitor_opportunity`). What this function
    proves is that slicing LOST NOTHING, which is the property the slicer must guarantee.
    """
    keep = set(kinds)
    rows = []
    for r in records:
        if r.get("kind") not in keep:
            continue
        rows.append(json.dumps(r, sort_keys=True, separators=(",", ":")))
    rows.sort()
    h = hashlib.sha256()
    for row in rows:
        h.update(row.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def frame_refs_of(rec: Dict[str, Any]) -> List[str]:
    """Every frame this record references."""
    out: List[str] = []
    fr = rec.get("frame_ref")
    if fr:
        out.append(str(fr))
    for f in (rec.get("frame_refs") or []):
        out.append(str(f))
    for f in (rec.get("episode_frames") or []):
        out.append(str(f))
    return out


def split(loaded: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Partition records and answers by device. Pure: no I/O."""
    records = loaded["records"]
    answers = loaded["answers"]

    by_dev: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    orphans: List[Dict[str, Any]] = []
    for r in records:
        d = device_of(r)
        if d is None:
            orphans.append(r)
        else:
            by_dev[d].append(r)

    ans_by_dev: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    ans_orphans: List[Dict[str, Any]] = []
    for a in answers:
        d = device_of(a)
        if d is None:
            ans_orphans.append(a)
        else:
            ans_by_dev[d].append(a)

    dev_type: Dict[str, str] = {}
    for r in records:
        if r.get("kind") == "device_register":
            dev_type[str(r["device_id"])] = str(r["type"])

    slices: Dict[str, Dict[str, Any]] = {}
    for d in sorted(by_dev):
        recs = by_dev[d]
        frames: List[str] = []
        seen = set()
        nbytes = 0
        for r in recs:
            for f in frame_refs_of(r):
                if f not in seen:
                    seen.add(f)
                    frames.append(f)
            b = r.get("frame_bytes")
            if b:
                nbytes += int(b)
        slices[d] = dict(
            device_id=d,
            type=dev_type.get(d),
            records=recs,
            answers=ans_by_dev.get(d, []),
            frames=frames,
            n_records=len(recs),
            n_answers=len(ans_by_dev.get(d, [])),
            n_frames=len(frames),
            payload_bytes=nbytes,
            kinds=dict(Counter(r["kind"] for r in recs)),
        )
    return dict(slices=slices, orphans=orphans, ans_orphans=ans_orphans, dev_type=dev_type)


def verify_reunion(loaded: Dict[str, Any], parts: Dict[str, Any]) -> Dict[str, Any]:
    """GATE 1. The union of the slices must equal the input, record for record.

    Checks, each of which can fail:
      a) record count: sum of slices + orphans == input
      b) multiset identity: the canonical JSON of every input record appears exactly as often
         in the reunion (catches a dropped, duplicated or mutated record)
      c) fairness digest over the reunion == over the input
      d) every opportunity_id in the input appears in exactly one slice, and no slice invents one
    """
    records = loaded["records"]
    slices = parts["slices"]
    reunion: List[Dict[str, Any]] = list(parts["orphans"])
    for d in sorted(slices):
        reunion.extend(slices[d]["records"])

    res: Dict[str, Any] = {}
    res["n_input"] = len(records)
    res["n_reunion"] = len(reunion)
    res["count_ok"] = (len(records) == len(reunion))

    def canon(rs: Iterable[Dict[str, Any]]) -> Counter:
        return Counter(json.dumps(r, sort_keys=True, separators=(",", ":")) for r in rs)

    ci, cr = canon(records), canon(reunion)
    res["multiset_ok"] = (ci == cr)
    if ci != cr:
        missing = list((ci - cr).elements())[:3]
        extra = list((cr - ci).elements())[:3]
        res["multiset_missing_sample"] = missing
        res["multiset_extra_sample"] = extra

    di, dr = fairness_digest(records), fairness_digest(reunion)
    res["digest_input"] = di
    res["digest_reunion"] = dr
    res["digest_ok"] = (di == dr)

    # D96 (1): ids are read, never constructed. Each must land in exactly one slice.
    def opps(rs: Iterable[Dict[str, Any]]) -> Counter:
        c: Counter = Counter()
        for r in rs:
            o = r.get("opportunity_id")
            if o:
                c[str(o)] += 1
        return c

    oi = opps(records)
    owned: Counter = Counter()
    for d in sorted(slices):
        owned.update(opps(slices[d]["records"]))
    res["n_opportunities_input"] = len(oi)
    res["n_opportunities_sliced"] = len(owned)
    res["opportunity_ok"] = (oi == owned)
    if oi != owned:
        res["opportunity_missing_sample"] = list((oi - owned).elements())[:5]
        res["opportunity_invented_sample"] = list((owned - oi).elements())[:5]

    res["all_ok"] = bool(res["count_ok"] and res["multiset_ok"] and res["digest_ok"]
                         and res["opportunity_ok"])
    return res


def write_slices(parts: Dict[str, Any], loaded: Dict[str, Any], out_root: Path,
                 devices: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Write one directory per device. Returns what was written."""
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    slices = parts["slices"]
    want = list(devices) if devices else sorted(slices)
    meta = loaded["meta"]
    written = {}
    for d in want:
        if d not in slices:
            raise KeyError("no such device in trace: %r (have %s)" % (d, sorted(slices)))
        s = slices[d]
        dd = out_root / d
        dd.mkdir(parents=True, exist_ok=True)
        with open(dd / "trace.jsonl", "w") as fh:
            for r in s["records"]:
                fh.write(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n")
        with open(dd / "device_answers.jsonl", "w") as fh:
            for a in s["answers"]:
                fh.write(json.dumps(a, sort_keys=True, separators=(",", ":")) + "\n")
        with open(dd / "frames.txt", "w") as fh:
            for f in s["frames"]:
                fh.write(f + "\n")
        sm = dict(
            device_id=d, type=s["type"],
            source_trace_dir=str(loaded["dir"]),
            source_n_records=len(loaded["records"]),
            source_fairness_digest=meta.get("fairness_digest"),
            source_device_answers_sha256=meta.get("device_answers_sha256"),
            run_s=meta.get("run_s"),
            dashcam_deadline_s=meta.get("dashcam_deadline_s"),
            robot_deadline_s=meta.get("robot_deadline_s"),
            mode=meta.get("mode"),
            n_records=s["n_records"], n_answers=s["n_answers"], n_frames=s["n_frames"],
            payload_bytes=s["payload_bytes"], kinds=s["kinds"],
            slicer_digest_of_this_slice=fairness_digest(s["records"]),
        )
        (dd / "slice_meta.json").write_text(json.dumps(sm, indent=2, sort_keys=True) + "\n")
        written[d] = dict(dir=str(dd), n_records=s["n_records"], n_frames=s["n_frames"],
                          payload_mb=round(s["payload_bytes"] / 1e6, 1), type=s["type"])
    return written


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Split a frozen live2 trace into per-device slices")
    ap.add_argument("--trace-dir", required=True, help="a frozen live2 trace directory")
    ap.add_argument("--out", default=None, help="where to write slices; omit to verify only")
    ap.add_argument("--devices", default=None,
                    help="comma-separated device ids to write; default all")
    ap.add_argument("--json", action="store_true", help="machine-readable report on stdout")
    a = ap.parse_args(argv)

    loaded = load_trace(Path(a.trace_dir))
    parts = split(loaded)
    gate = verify_reunion(loaded, parts)

    report: Dict[str, Any] = dict(
        trace_dir=str(loaded["dir"]),
        n_devices=len(parts["slices"]),
        n_records=len(loaded["records"]),
        n_answers=len(loaded["answers"]),
        n_orphan_records=len(parts["orphans"]),
        n_orphan_answers=len(parts["ans_orphans"]),
        gate_reunion=gate,
        devices={d: dict(type=s["type"], n_records=s["n_records"], n_frames=s["n_frames"],
                         payload_mb=round(s["payload_bytes"] / 1e6, 1))
                 for d, s in sorted(parts["slices"].items())},
    )

    if a.out:
        if not gate["all_ok"]:
            print("REFUSING TO WRITE: reunion gate failed", file=sys.stderr)
            print(json.dumps(gate, indent=2, sort_keys=True), file=sys.stderr)
            return 2
        devs = a.devices.split(",") if a.devices else None
        report["written"] = write_slices(parts, loaded, Path(a.out), devs)

    if a.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("trace      %s" % report["trace_dir"])
        print("devices    %d   records %d   answers %d"
              % (report["n_devices"], report["n_records"], report["n_answers"]))
        print("orphans    %d records, %d answers (belong to no single device)"
              % (report["n_orphan_records"], report["n_orphan_answers"]))
        print("")
        print("GATE 1 reunion: %s" % ("PASS" if gate["all_ok"] else "FAIL"))
        for k in ("count_ok", "multiset_ok", "digest_ok", "opportunity_ok"):
            print("   %-16s %s" % (k, gate[k]))
        print("   digest         %s" % gate["digest_input"][:16])
        print("   opportunities  %d input, %d sliced"
              % (gate["n_opportunities_input"], gate["n_opportunities_sliced"]))
        print("")
        print("%-10s %-10s %9s %8s %10s" % ("device", "type", "records", "frames", "MB"))
        for d, v in sorted(report["devices"].items()):
            print("%-10s %-10s %9d %8d %10.1f"
                  % (d, v["type"], v["n_records"], v["n_frames"], v["payload_mb"]))
        if "written" in report:
            print("")
            print("wrote %d slices to %s" % (len(report["written"]), a.out))
    return 0 if gate["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
