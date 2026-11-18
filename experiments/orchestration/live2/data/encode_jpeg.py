#!/usr/bin/env python3
"""Encode the round-1 wire frames to JPEG ONCE and store them (D70, D91). DO NOT RUN ON FLASH.

StudyLIVE2-fleet, part 2. This script must run on the host that HOLDS THE FRAMES. The flash box
has none of them: `~/data/dashcam/d14_frames/small`, `~/data/dashcam/d14b_frames/small`,
`~/.cache/fm-switching/sember_frames` and `~/.cache/fm-switching/r1_inputs` are all absent here
and `/home/nesl` is permission denied. It was written on flash and NOT executed; nothing in this
directory has produced a byte of output.

WHY IT EXISTS (D91). The stored JPEGs are the SINGLE SOURCE for both the pending 32B JPEG
calibration refit (D86) and the live run, so calibration and evaluation see byte-identical
inputs. Encoding twice, once per consumer, would reintroduce exactly the mismatch D91 closes.

THE RECIPE IS THE RECOVERED E10a RECIPE, NOT A NEW ONE

Nexar, quality 90 (`experiments/cost/study_e10a_parity_vllm.py` lines 73-87):

    im = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    buf = io.BytesIO(); im.save(buf, format="JPEG", quality=90)

Input is the STORED SMALL PNG bytes, decoded then re-encoded, pixel grid unchanged at 768x432
(StudyD14 SMALL frames, LANCZOS-resized lossless PNG). No resize happens in the encode step.

S-EMBER, quality 88 (`experiments/cost/study_e10a_parity_vllm.py` lines 133-144):

    Image.fromarray(np.ascontiguousarray(fr.transpose(1, 2, 0))).save(buf, format="JPEG",
                                                                      quality=88)

Input for RICH and RECENT is the already-final-size frames of StudyR1's npz (CHW uint8,
transposed to HWC), 352x256 and 512x384. D2 is NOT an r1_inputs construction: E10a built it from
the raw `sember_frames` cache with `study_rh3_inputs.load(path, (352, 256))`, which is what
`iter_sember_d2` does, so a D2 frame is portrait-or-landscape 352x256 as that loader orients it. The wire form for S-EMBER is ONE
`data:video/jpeg;base64,` URL whose per-frame base64 strings are COMMA-JOINED; that is part of
the recipe and `--emit-request-sizes` reproduces it so the per-request base64 size can be checked
against E10a's committed `request_bytes`.

In every case: PIL only. No cv2, no ffmpeg, no `optimize`, no `progressive`, no explicit
`subsampling`, no `qtables`. PIL writes YCbCr with its defaults, which is 4:2:0 at these quality
values.

BYTE-EXACTNESS TO E10a IS NOT CLAIMED (D91). The E10a JPEG outputs were never stored - every
E10a encode went to an in-memory BytesIO and was base64'd straight into a request body - so there
is nothing to diff against. The Pillow version used by E10a is also not recorded in
`e10a_run_meta_h100nvl.json` or in `e10a_sizes.json`'s provenance, and PIL's default chroma
subsampling and quantisation tables are version-sensitive. So this script RECORDS the Pillow and
libjpeg versions it used, and `build_manifest.py` checks the resulting byte DISTRIBUTION against
E10a's committed quartiles and per-request sizes. That is a distributional check, not a
reproduction.

USAGE (on the frame host)

  python3 encode_jpeg.py --dataset nexar \\
      --src ~/data/dashcam/d14b_frames/small:~/data/dashcam/d14_frames/small \\
      --out ~/data/live2/jpeg/nexar_q90
  python3 encode_jpeg.py --dataset sember --construction D2 \\
                         --src ~/.cache/fm-switching/sember_frames \\
                         --out ~/data/live2/jpeg/sember_d2_q88
  python3 build_manifest.py --store ~/data/live2/jpeg/nexar_q90 --dataset nexar
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[4]
NEXAR_QUALITY = 90          # E10a Job A
SEMBER_QUALITY = 88         # E10a Job A / E10a-full
NEXAR_EXPECT_SIZE = (768, 432)
SEMBER_EXPECT_SIZE = {"D2": (352, 256), "RICH": (352, 256), "RECENT": (512, 384)}


def versions() -> Dict[str, Any]:
    """Every version that can move a JPEG byte, recorded in the manifest (D91)."""
    import PIL
    from PIL import features
    out: Dict[str, Any] = dict(
        pillow=PIL.__version__,
        libjpeg=features.version("jpg"),
        libjpeg_turbo=features.version("jpg_2000") if False else features.version("jpg"),
        jpeg_codec=features.version_codec("jpg"),
        python=sys.version.split()[0],
        platform=platform.platform(),
    )
    try:
        import numpy
        out["numpy"] = numpy.__version__
    except Exception:
        out["numpy"] = None
    out["features_pilinfo"] = {k: features.check(k) for k in ("jpg", "jpg_2000", "zlib")}
    return out


# ---------------------------------------------------------------- the two encoders
def jpeg_bytes_from_png(png_bytes: bytes, quality: int = NEXAR_QUALITY) -> bytes:
    """E10a Job A, Nexar. Byte-for-byte the committed function, including `.convert("RGB")`."""
    from PIL import Image
    im = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    if im.size != NEXAR_EXPECT_SIZE:
        raise ValueError(f"Nexar frame is {im.size}, expected {NEXAR_EXPECT_SIZE}; the encode "
                         f"step must not resize (StudyD14 SMALL frames are already 768x432)")
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def jpeg_bytes_from_chw(fr, quality: int = SEMBER_QUALITY,
                        expect: Optional[Tuple[int, int]] = None) -> bytes:
    """E10a Job A, S-EMBER. `fr` is CHW uint8 as StudyR1's npz stores it."""
    import numpy as np
    from PIL import Image
    im = Image.fromarray(np.ascontiguousarray(fr.transpose(1, 2, 0)))
    if expect is not None and im.size != expect:
        raise ValueError(f"S-EMBER frame is {im.size}, expected {expect}")
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


# ---------------------------------------------------------------- sources
# THE STORE LAYOUTS THE H100 ACTUALLY USED (StudyLIVE2-pre section 2, OVERNIGHT DECISIONS 1-2).
# Both parsers were written on flash without the data and neither matched the frame host:
#
#   1. Nexar frames are stored `<src>/<clip>/<pts_ms>.png` (`experiments/dashcam/d14b_prepare.py`
#      lines 84-87 and 156), not `<clip>_t<seconds>.png`; run as written, every frame would have
#      been stored UNPARSED. The frame for instant (clip, t) is the one the committed D14b N = 1
#      request used: `results/dashcam/study_d14b/d14b_requests_manifest.jsonl.gz`, `frame_keys[0]`
#      (the latest frame with pts <= t), with `small_sha256[0]` verified on every frame read.
#
#   2. S-EMBER D2 is not an `r1_inputs` construction - that cache holds only RICH and RECENT npz -
#      so there is no CHW array to transpose. E10a built D2 from the raw `sember_frames` cache
#      with `study_rh3_inputs.load(path, (352, 256))` (`experiments/cost/study_e10a_sizes.py`
#      lines 84-85), which returns a PIL image already at the final size; the stride is the
#      committed D2 stride of 2 s (StudyRH4 / RH6).
#
# The frame references are unchanged: `fleet/trace.py:295` and `:357,390` put
# `<clip>.mp4|t<tttt.tt>` and `<session>|f<ffffff.ff>` on the wire, and that is what is stored.
D14B_MANIFEST = REPO / "results/dashcam/study_d14b/d14b_requests_manifest.jsonl.gz"
D2_STRIDE_S = 2.0
D2_SIZE_HW = (352, 256)


def iter_nexar(src: Path) -> Iterator[Tuple[str, bytes]]:
    """(frame_ref, png_bytes) for every dense instant, via the committed D14b N = 1 manifest.

    `src` may be several frame roots separated by `os.pathsep`, because StudyD14b hard-links the
    frames it shares with StudyD14 and the two pools are separate directories.
    """
    import gzip
    roots = [Path(x).expanduser() for x in str(src).split(os.pathsep) if x]
    if not D14B_MANIFEST.exists():
        raise SystemExit(f"MISSING: {D14B_MANIFEST}; the Nexar parser reads the committed D14b "
                         f"N = 1 request manifest, it does not glob the frame directory")
    seen: Dict[Tuple[str, str], bytes] = {}
    for ln in gzip.open(D14B_MANIFEST, "rt"):
        r = json.loads(ln)
        if int(r["n"]) != 1:
            continue
        clip, key = str(r["file_name"]), str(r["frame_keys"][0])
        want = str(r["small_sha256"][0])
        cached = seen.get((clip, key))
        if cached is None:
            stem = clip.replace(".mp4", "")
            paths = [root / stem / f"{key}.png" for root in roots]
            hit = next((q for q in paths if q.exists()), None)
            if hit is None:
                raise SystemExit(f"MISSING frame {stem}/{key}.png under "
                                 f"{[str(x) for x in roots]}; nothing is substituted")
            cached = hit.read_bytes()
            got = hashlib.sha256(cached).hexdigest()
            if got != want:
                raise SystemExit(f"{hit}: sha256 {got} != the manifest's {want}")
            seen[(clip, key)] = cached
        yield f"{clip}|t{float(r['t']):07.2f}", cached


def iter_sember_d2(src: Path) -> Iterator[Tuple[str, Any]]:
    """(frame_ref, PIL image) for the D2 frames of every committed EVAL session.

    E10a's own D2 loader is used (`study_rh3_inputs.load`), so no resize is reinvented here.
    """
    sys.path.insert(0, str(REPO / "experiments/sember"))
    sys.path.insert(0, str(REPO / "experiments/orchestration/live2/fleet"))
    import data_sources as DS
    import study_rh3_inputs as B3
    B3.FRAMES = Path(src).expanduser()
    for sid, meta in sorted(DS.eval_sessions().items()):
        idx = B3.frames_index(sid)
        last_q = max(q.t_ask for q in meta.questions)
        ts = sorted(t for t in idx if t % D2_STRIDE_S == 0 and t <= last_q + 1e-9)
        for t in ts:
            yield f"{sid}|f{float(t):08.2f}", B3.load(idx[t], D2_SIZE_HW)


def iter_sember(src: Path, construction: str) -> Iterator[Tuple[str, Any]]:
    """(frame_ref, CHW uint8 frame) over StudyR1's per-request npz inputs.

    Only RICH and RECENT live in `r1_inputs`; D2 goes through `iter_sember_d2` instead.
    """
    import numpy as np
    for p in sorted(Path(src).expanduser().rglob("*.npz")):
        z = np.load(p)
        key = next((k for k in ("frames", "images", "arr_0") if k in z.files), None)
        if key is None:
            raise ValueError(f"{p}: no frames array (files={z.files}); inspect before encoding")
        arr = z[key]
        ts = z["frame_t"] if "frame_t" in z.files else range(len(arr))
        vid = p.stem
        for i, fr in enumerate(arr):
            t = float(ts[i]) if i < len(ts) else float(i)
            yield f"{vid}|{construction}|f{t:08.2f}", fr


def jpeg_bytes_from_image(im, quality: int = SEMBER_QUALITY) -> bytes:
    """E10a's `enc(im, "jpeg", q)` (`experiments/cost/study_e10a_sizes.py` lines 41-49)."""
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


# ---------------------------------------------------------------- driver
def encode(dataset: str, src: Path, out: Path, construction: str = "D2",
           limit: Optional[int] = None, emit_request_sizes: bool = False) -> Dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    frames_dir = out / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    log = out / "encode_log.jsonl"
    quality = NEXAR_QUALITY if dataset == "nexar" else SEMBER_QUALITY
    n = 0
    sizes: List[int] = []
    per_request: Dict[str, int] = {}
    with open(log, "w") as fh:
        if dataset == "nexar":
            it: Iterator[Tuple[str, Any]] = iter_nexar(src)
        elif construction == "D2":
            it = iter_sember_d2(src)
        else:
            it = iter_sember(src, construction)
        for ref, payload in it:
            if dataset == "nexar":
                jb = jpeg_bytes_from_png(payload, quality)
            elif construction == "D2":
                jb = jpeg_bytes_from_image(payload, quality)
            else:
                jb = jpeg_bytes_from_chw(payload, quality,
                                         SEMBER_EXPECT_SIZE.get(construction))
            rel = ref.replace("|", "__").replace("/", "_") + ".jpg"
            (frames_dir / rel).write_bytes(jb)
            sizes.append(len(jb))
            if emit_request_sizes:
                vid = ref.split("|", 1)[0]
                # The S-EMBER wire form: ONE data:video/jpeg URL, per-frame base64 COMMA-JOINED.
                per_request[vid] = per_request.get(vid, 0) + \
                    len(base64.b64encode(jb)) + (1 if vid in per_request else 0)
            fh.write(json.dumps(dict(frame_ref=ref, file=rel, bytes=len(jb)),
                                sort_keys=True) + "\n")
            n += 1
            if limit is not None and n >= limit:
                break
    meta = dict(dataset=dataset, construction=(construction if dataset == "sember" else None),
                quality=quality, src=str(src), out=str(out), n_frames=n,
                recipe=("PIL Image.save(format='JPEG', quality=%d); no optimize, no progressive, "
                        "no explicit subsampling, no qtables; PIL YCbCr defaults (4:2:0 at this "
                        "quality); NO resize in the encode step" % quality),
                recipe_source="experiments/cost/study_e10a_parity_vllm.py (E10a Job A)",
                byte_exactness_to_e10a="NOT CLAIMED (D91): E10a stored no JPEG output and "
                                       "recorded no Pillow version",
                versions=versions(),
                per_request_base64_bytes=(per_request or None))
    (out / "encode_meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    return meta


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", required=True, choices=("nexar", "sember"))
    ap.add_argument("--construction", default="D2", choices=tuple(SEMBER_EXPECT_SIZE))
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--emit-request-sizes", action="store_true")
    a = ap.parse_args(argv)
    src = Path(a.src).expanduser()
    if not src.exists():
        raise SystemExit(f"MISSING: {src} does not exist. This script must run on the host that "
                         f"holds the frames; it does not run on flash.")
    m = encode(a.dataset, src, Path(a.out).expanduser(), a.construction, a.limit,
               a.emit_request_sizes)
    print(json.dumps(m, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
