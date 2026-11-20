#!/usr/bin/env python3
"""Rescore the committed RefSpatial runs with the fixed point parser. RUNS WHERE THE MASKS ARE.

  python3 -I experiments/casestudy/ss2_refspatial_rescore.py --data /dev/shm/ss2_data

User instruction 2026-11-20. `ss2_bench_kit._iter_json_points` now accepts the {"x": .., "y": ..}
object form, which four CLOUD replies used and which parsed to zero points before the fix (see
reports/study_ss2.md section 11.4 and ss2_parser_fix_proof.json). The parse change is already
proven; this recomputes the SCORES, which needs the ground-truth masks.

IT RECORDS A SHA256 PER MASK, which the committed manifest does not. That gap is why this belongs
on the box holding the originals rather than on a box where the masks were re-staged: the mask is
an input to every score, and without a hash a re-staged mask cannot be shown to be the one the
committed run scored against. After this runs, that is no longer true of RefSpatial.

Nothing is overwritten. The old per-question scores are carried beside the new ones, and the
output names both, so every table can state which it used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT / "experiments/lib"), str(ROOT / "experiments/casestudy")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from _provenance import stamp  # noqa: E402

SS2 = ROOT / "results/casestudy/study_ss2"
OUT = SS2 / "refspatial_rescore.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="the SS2 data root holding refspatial_img/")
    a = ap.parse_args()
    import ss2_bench_kit as K
    DATA = Path(a.data).expanduser()
    man = {}
    with (SS2 / "refspatial_manifest.jsonl").open() as fh:
        for ln in fh:
            r = json.loads(ln)
            man[r["qid"]] = r

    mask_sha, mask_cache = {}, {}

    def mask_for(qid):
        rel = man[qid]["mask"]
        if rel not in mask_cache:
            p = DATA / rel
            if not p.exists():
                raise SystemExit(f"MISSING mask {p}; nothing is substituted")
            b = p.read_bytes()
            mask_sha[rel] = hashlib.sha256(b).hexdigest()
            mask_cache[rel] = K.load_binary_mask(str(p))
        return mask_cache[rel]

    out = dict(
        label="RefSpatial rescore with the fixed point parser, with a sha256 per ground-truth "
              "mask. Old per-question scores are carried beside the new ones; nothing is "
              "overwritten.",
        at=datetime.now().isoformat(), data_root=str(DATA), tiers={})
    for tier in ("device", "cloud32b"):
        doc = json.loads((SS2 / f"refspatial_{tier}.json").read_text())
        moved, rows = [], []
        for r in doc["rows"]:
            m = man[r["qid"]]
            mask = mask_for(r["qid"])
            H, W = mask.shape[:2]
            pts = K.refspatial_parse_points(r["answer_raw"] or "", W, H)
            acc = K.refspatial_point_accuracy(pts, mask)
            old = float(r["score"]["point_accuracy"])
            rows.append(dict(qid=r["qid"], split=m["split"],
                             point_accuracy_old=old, point_accuracy_new=float(acc),
                             n_points_old=int(r["score"]["n_points"]), n_points_new=int(len(pts)),
                             mask=m["mask"], mask_sha256=mask_sha[m["mask"]]))
            if abs(acc - old) > 1e-12 or len(pts) != int(r["score"]["n_points"]):
                moved.append(rows[-1])
        by_split = {}
        for sp in sorted({r["split"] for r in rows}):
            sel = [r for r in rows if r["split"] == sp]
            by_split[sp] = dict(
                n=len(sel),
                old=float(np.mean([r["point_accuracy_old"] for r in sel])),
                new=float(np.mean([r["point_accuracy_new"] for r in sel])))
        out["tiers"][tier] = dict(
            n=len(rows), n_moved=len(moved), moved=moved,
            overall_old=float(np.mean([r["point_accuracy_old"] for r in rows])),
            overall_new=float(np.mean([r["point_accuracy_new"] for r in rows])),
            by_split=by_split, rows=rows)
    d, c = out["tiers"]["device"], out["tiers"]["cloud32b"]
    out["delta"] = dict(old=c["overall_old"] - d["overall_old"],
                        new=c["overall_new"] - d["overall_new"])
    out["mask_sha256"] = mask_sha
    out["control"] = dict(
        device_rows_moved=d["n_moved"],
        expectation="ZERO device rows may move: the fix only adds a form no device reply used "
                    "(ss2_parser_fix_proof.json). A non-zero count here means the rescore is not "
                    "the fix alone and must be investigated before any number is read.",
        passed=(d["n_moved"] == 0))
    out["_provenance"] = stamp(script="ss2_refspatial_rescore.py", model="none", device="cpu",
                               n=d["n"] + c["n"], args=a)
    OUT.write_text(json.dumps(out, indent=1))
    print(f"wrote {OUT}")
    print(f"  device moved {d['n_moved']} (must be 0)  cloud moved {c['n_moved']}")
    print(f"  device {d['overall_old']:.4f} -> {d['overall_new']:.4f}")
    print(f"  cloud  {c['overall_old']:.4f} -> {c['overall_new']:.4f}")
    print(f"  delta  {out['delta']['old']:+.4f} -> {out['delta']['new']:+.4f}")
    print(f"  masks hashed: {len(mask_sha)}")
    if not out["control"]["passed"]:
        raise SystemExit("CONTROL FAILED: a device row moved; see refspatial_rescore.json")


if __name__ == "__main__":
    main()
