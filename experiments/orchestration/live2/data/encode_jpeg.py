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

Input is the already-final-size frames of StudyR1's npz (CHW uint8, transposed to HWC), so RICH
and D2 are 352x256 and RECENT is 512x384. The wire form for S-EMBER is ONE
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

  python3 encode_jpeg.py --dataset nexar  --src ~/data/dashcam/d14_frames/small \\
                         --out ~/data/live2/jpeg/nexar_q90
  python3 encode_jpeg.py --dataset sember --construction D2 \\
                         --src ~/.cache/fm-switching/r1_inputs \\
                         --out ~/data/live2/jpeg/sember_d2_q88
  python3 build_manifest.py --store ~/data/live2/jpeg/nexar_q90 --dataset nexar
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import platform
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

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
def iter_nexar(src: Path) -> Iterator[Tuple[str, bytes]]:
    """(frame_ref, png_bytes) over a StudyD14 / D14b SMALL frame directory.

    frame_ref is `<clip>.mp4|t<tttt.tt>`, matching what `fleet/trace.py` puts on the wire. The
    filename convention of the committed frame pools is `<clip>_t<seconds>.png`; anything this
    cannot parse is reported and skipped, never guessed at.
    """
    for p in sorted(src.rglob("*.png")):
        stem = p.stem
        if "_t" not in stem:
            yield f"UNPARSED|{p.name}", p.read_bytes()
            continue
        clip, t = stem.rsplit("_t", 1)
        try:
            tv = float(t.replace("_", "."))
        except ValueError:
            yield f"UNPARSED|{p.name}", p.read_bytes()
            continue
        yield f"{clip}.mp4|t{tv:07.2f}", p.read_bytes()


def iter_sember(src: Path, construction: str) -> Iterator[Tuple[str, Any]]:
    """(frame_ref, CHW uint8 frame) over StudyR1's per-request npz inputs."""
    import numpy as np
    for p in sorted(src.rglob("*.npz")):
        z = np.load(p)
        key = None
        for k in ("frames", "images", "arr_0"):
            if k in z.files:
                key = k
                break
        if key is None:
            raise ValueError(f"{p}: no frames array (files={z.files}); inspect before encoding")
        arr = z[key]
        ts = z["frame_t"] if "frame_t" in z.files else range(len(arr))
        vid = p.stem
        for i, fr in enumerate(arr):
            t = float(ts[i]) if i < len(ts) else float(i)
            yield f"{vid}|{construction}|f{t:08.2f}", fr


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
        it = iter_nexar(src) if dataset == "nexar" \
            else iter_sember(src, construction)
        for ref, payload in it:
            if dataset == "nexar":
                jb = jpeg_bytes_from_png(payload, quality)
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
