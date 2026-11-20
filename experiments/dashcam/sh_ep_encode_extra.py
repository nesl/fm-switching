#!/usr/bin/env python3
"""StudySH-EP: add the 165 missing JPEGs to the D91 nexar store. RUNS ON THE FRAME HOST ONLY.

  python3 -I experiments/dashcam/sh_ep_encode_extra.py \\
      --src ~/data/dashcam/d14b_frames/small:~/data/dashcam/d14_frames/small \\
      --store ~/data/live2/jpeg/nexar_q90 [--dry-run]

WHY ANY FILE IS MISSING AT ALL
  `live2/data/encode_jpeg.py:iter_nexar` walks the committed D14b N = 1 request rows and nothing
  else, so the store holds one JPEG per decision time t >= 3.0 and none below. StudySH-EP's EP-G
  context reaches 10 s before the reference time, so for 32 clips with a small reference time
  some context instants fall below 3.0 s. Their PNGs ARE rendered (they are D14b N = 3 targets,
  and every one is in D14b's committed sha256 manifest), so the only thing missing is the encode.

WHAT THIS DOES, AND WHAT IT REFUSES TO DO
  It encodes exactly the frames listed in `sh_ep_store_extension.jsonl.gz`, by calling
  `encode_jpeg.jpeg_bytes_from_png` - the committed D91 recipe function, imported, not retyped -
  and writes them under the store's own naming (`frames/<clip>__t<t>.jpg`). It verifies each
  source PNG against D14b's committed sha256 before encoding. It REFUSES to overwrite an existing
  file, so no existing JPEG can be touched (D91), and it appends to the store's `encode_log.jsonl`
  rather than rewriting it. It records the Pillow and libjpeg versions it ran with, which will
  differ from the original encode run if the host has been updated since; that is reported, not
  hidden, and the report states that these 165 frames are the only ones in the study whose encode
  provenance differs from the rest.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/lib"))
sys.path.insert(0, str(ROOT / "experiments/orchestration/live2/data"))
from _provenance import stamp  # noqa: E402

import encode_jpeg as E  # noqa: E402

LIST = ROOT / "results/dashcam/study_sh_ep/sh_ep_store_extension.jsonl.gz"
OUT = ROOT / "results/dashcam/study_sh_ep"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="PNG roots, os.pathsep separated")
    ap.add_argument("--store", required=True, help="the D91 nexar q90 store root")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    roots = [Path(x).expanduser() for x in str(a.src).split(os.pathsep) if x]
    store = Path(a.store).expanduser()
    frames = store / "frames"
    if not frames.is_dir():
        raise SystemExit(f"{frames} is not a directory; this is not the D91 nexar store")

    rows = [json.loads(ln) for ln in gzip.open(LIST, "rt")]
    wrote, existed, sizes, bad = [], [], [], []
    for r in rows:
        dst = store / r["store_file"]
        if dst.exists():
            existed.append(r["store_file"])
            continue
        stem = r["file_name"].replace(".mp4", "")
        src = next((q for q in (root / stem / f"{r['key']}.png" for root in roots)
                    if q.exists()), None)
        if src is None:
            bad.append(dict(frame=r["store_file"], why="PNG not found",
                            looked=[str(root / stem / f"{r['key']}.png") for root in roots]))
            continue
        b = src.read_bytes()
        got = hashlib.sha256(b).hexdigest()
        if got != r["small_sha256"]:
            bad.append(dict(frame=r["store_file"], why="sha256 mismatch against the committed "
                            "D14b manifest", expected=r["small_sha256"], got=got))
            continue
        jb = E.jpeg_bytes_from_png(b, E.NEXAR_QUALITY)
        sizes.append(len(jb))
        if not a.dry_run:
            dst.write_bytes(jb)
            with (store / "encode_log.jsonl").open("a") as fh:
                fh.write(json.dumps(dict(frame_ref=r["store_ref"],
                                         file=r["store_file"].split("/", 1)[-1],
                                         bytes=len(jb), added_by="StudySH-EP"),
                                    sort_keys=True) + "\n")
        wrote.append(r["store_file"])

    meta = dict(label="StudySH-EP store extension: the frames below the committed 3.0 s decision "
                      "grid, encoded with the committed D91 nexar recipe. No existing file was "
                      "overwritten.",
                quality=E.NEXAR_QUALITY, recipe_source="live2/data/encode_jpeg.jpeg_bytes_from_png",
                store=str(store), src=[str(r) for r in roots], dry_run=bool(a.dry_run),
                requested=len(rows), written=len(wrote), already_present=len(existed),
                failed=bad, versions=E.versions(),
                bytes=dict(n=len(sizes), total=sum(sizes),
                           min=min(sizes) if sizes else None,
                           max=max(sizes) if sizes else None,
                           mean=(sum(sizes) / len(sizes)) if sizes else None),
                at=datetime.now().isoformat())
    meta["_provenance"] = stamp(script="sh_ep_encode_extra.py", model="none",
                                device=os.uname().nodename, n=len(wrote), args=a)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sh_ep_store_extension_meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps({k: v for k, v in meta.items() if k != "_provenance"}, indent=1))
    if bad:
        raise SystemExit(f"{len(bad)} frames could not be added; nothing is substituted")


if __name__ == "__main__":
    main()
