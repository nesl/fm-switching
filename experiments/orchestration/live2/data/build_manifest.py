#!/usr/bin/env python3
"""Manifest of the stored round-1 JPEGs, with the E10a distributional check. DO NOT RUN ON FLASH.

StudyLIVE2-fleet, part 2, second half. Runs on the host that holds the frames, after
`encode_jpeg.py`. Written on flash and NOT executed.

WHAT IT PRODUCES

  manifest.jsonl      one row per stored frame: frame_ref, path, bytes, sha256
  manifest_meta.json  the versions carried over from encode_meta.json, the byte distribution of
                      the store, and the E10a comparison

The manifest is what `fleet/trace.py --frame-manifest` reads, so the live run charges the uplink
the ACTUAL byte count of each frame instead of the committed median. It is also what the pending
32B JPEG refit (D86) must read, so both consumers see the same bytes (D91).

THE CHECK (D91: the check is against E10a's COMMITTED BYTE QUARTILES and per-request base64
sizes; byte-exactness to E10a is not claimed)

E10a stored no JPEG output and recorded no Pillow version, so there is nothing to diff. What can
be compared is the distribution, read live from `results/cost/study_e10/e10a_sizes.json`:

  nexar   jpeg90 at 768x432          p25 / median / p75 / mean over 500 frames
  sember  jpeg88 per (construction|HxW)   p25 / median / p75 / mean
  sember  request_bytes per construction  the comma-joined base64 body size over 845 requests

A quartile is FLAGGED if it differs by more than `--tol` (default 10 %) from the committed value.
A flag is not a failure of this script: it says the encoder's byte behaviour has moved, which is
the version sensitivity D91 warns about, and it must be reported before the stored JPEGs are used
for either consumer. The script exits non-zero on any flag so a pipeline cannot walk past it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

E10A_SIZES_REL = "results/cost/study_e10/e10a_sizes.json"


def _repo_root(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "research/EXPERIMENTS.md").exists():
            return p
    raise SystemExit("cannot locate the repository root (research/EXPERIMENTS.md not found)")


def sha256_of(p: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def quartiles(v: Sequence[int]) -> Dict[str, float]:
    s = sorted(v)
    if not s:
        return dict(n=0)
    def q(p: float) -> float:
        return float(statistics.quantiles(s, n=4)[p]) if len(s) > 3 else float(s[0])
    return dict(n=len(s), p25=q(0), median=float(statistics.median(s)), p75=q(2),
                mean=float(statistics.fmean(s)), min=float(s[0]), max=float(s[-1]))


def compare(got: Dict[str, float], want: Dict[str, Any], tol: float) -> Dict[str, Any]:
    rows = []
    for k in ("p25", "median", "p75", "mean"):
        if k not in got or k not in want or not want[k]:
            continue
        ratio = got[k] / float(want[k])
        rows.append(dict(stat=k, this_run=round(got[k], 2), e10a=float(want[k]),
                         ratio=round(ratio, 5), flagged=abs(ratio - 1.0) > tol))
    return dict(rows=rows, any_flagged=any(r["flagged"] for r in rows))


def build(store: Path, dataset: str, tol: float, root: Path) -> Dict[str, Any]:
    frames = store / "frames"
    if not frames.exists():
        raise SystemExit(f"MISSING: {frames}; run encode_jpeg.py first, on the frame host")
    enc_meta = json.loads((store / "encode_meta.json").read_text())
    log = {r["file"]: r["frame_ref"]
           for r in (json.loads(l) for l in open(store / "encode_log.jsonl"))}
    rows: List[Dict[str, Any]] = []
    for p in sorted(frames.rglob("*.jpg")):
        rel = str(p.relative_to(frames))
        rows.append(dict(frame_ref=log.get(rel, rel), path=str(p), bytes=p.stat().st_size,
                         sha256=sha256_of(p)))
    with open(store / "manifest.jsonl", "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")

    e10a = json.loads((root / E10A_SIZES_REL).read_text())
    got = quartiles([r["bytes"] for r in rows])
    if dataset == "nexar":
        checks = {"nexar jpeg90 768x432":
                  compare(got, e10a["nexar"]["bytes"]["jpeg90"], tol)}
    else:
        con = enc_meta.get("construction") or "D2"
        per = e10a["sember"]["per_resolution"]
        keys = [k for k in per if k.startswith(con + "|")]
        checks = {}
        for k in keys:
            w = per[k]["bytes"].get("jpeg88")
            if w and w.get("n"):
                checks[f"sember jpeg88 {k}"] = compare(got, w, tol)
        rb = e10a["sember"].get("request_bytes", {}).get(con, {}).get("jpeg88")
        pr = enc_meta.get("per_request_base64_bytes")
        if rb and pr:
            checks[f"sember request base64 {con}"] = compare(
                quartiles(list(pr.values())), rb, tol)
    meta = dict(store=str(store), dataset=dataset, n_frames=len(rows), tol=tol,
                bytes=got, versions=enc_meta.get("versions"),
                quality=enc_meta.get("quality"), recipe=enc_meta.get("recipe"),
                byte_exactness_to_e10a=enc_meta.get("byte_exactness_to_e10a"),
                e10a_source=E10A_SIZES_REL, e10a_checks=checks,
                any_flagged=any(c["any_flagged"] for c in checks.values()),
                note=("A flagged quartile means the encoder's byte behaviour differs from E10a's "
                      "by more than the tolerance. D91 does not claim byte-exactness, so a flag "
                      "is a REPORTABLE difference, not a script failure; it must be reported "
                      "before these JPEGs feed the 32B refit (D86) or the live run."))
    (store / "manifest_meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    return meta


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--store", required=True)
    ap.add_argument("--dataset", required=True, choices=("nexar", "sember"))
    ap.add_argument("--tol", type=float, default=0.10)
    a = ap.parse_args(argv)
    here = Path(__file__).resolve().parent
    m = build(Path(a.store).expanduser(), a.dataset, a.tol, _repo_root(here))
    print(json.dumps(m, indent=2, sort_keys=True))
    return 2 if m["any_flagged"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
