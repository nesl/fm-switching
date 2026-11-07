"""StudyB1-flash frame rendering. Decode-timestamp frame selection with PyAV.

Spec (fixed; the H100 run uses this same file, identified by its SHA-256):
  - each target time takes the LATEST decoded frame whose pts <= target
  - no frame may be later than the query time (asserted)
  - RECENT: N=9 targets evenly spaced over [t-3, t]  (shorter span logged when t < 3)
  - HISTORY: N=37 targets evenly spaced over [0, t]  (whole video when t is None)
  - resize LANCZOS to 768x432, encode lossless PNG
  - frames are never written to disk; a bounded in-memory cache only
"""
from __future__ import annotations

import hashlib
import io
import threading
from collections import OrderedDict

import av
from PIL import Image

RECENT_N = 9
RECENT_SPAN_S = 3.0
HISTORY_N = 37
OUT_W, OUT_H = 768, 432

_CACHE_MAX_BYTES = 6 * 1024**3
_cache: "OrderedDict[tuple, tuple]" = OrderedDict()
_cache_bytes = 0
_cache_lock = threading.Lock()
_hits = 0
_misses = 0


def versions() -> dict:
    lv = dict(av.library_versions)
    return {
        "pyav": av.__version__,
        "ffmpeg_libavcodec": ".".join(map(str, lv["libavcodec"])),
        "ffmpeg_libavformat": ".".join(map(str, lv["libavformat"])),
        "ffmpeg_libavutil": ".".join(map(str, lv["libavutil"])),
        "pillow": Image.__version__,
    }


def cache_stats() -> dict:
    with _cache_lock:
        return {"entries": len(_cache), "bytes": _cache_bytes, "hits": _hits, "misses": _misses}


def _cache_get(key):
    global _hits, _misses
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            _hits += 1
            return _cache[key]
        _misses += 1
        return None


def _cache_put(key, val: tuple):
    global _cache_bytes
    with _cache_lock:
        if key in _cache:
            return
        _cache[key] = val
        _cache_bytes += len(val[0])
        while _cache_bytes > _CACHE_MAX_BYTES and _cache:
            _, v = _cache.popitem(last=False)
            _cache_bytes -= len(v[0])


def duration_s(path: str) -> float:
    with av.open(path) as c:
        vs = c.streams.video[0]
        if vs.duration is not None and vs.time_base is not None:
            return float(vs.duration * vs.time_base)
        if c.duration is not None:
            return float(c.duration / av.time_base)
    raise RuntimeError(f"no duration for {path}")


def targets_recent(t: float) -> tuple[list[float], float]:
    """N=9 targets evenly spaced over [t-3, t]; span shortened (and returned) when t < 3."""
    lo = max(0.0, t - RECENT_SPAN_S)
    span = t - lo
    if RECENT_N == 1:
        return [t], span
    step = span / (RECENT_N - 1)
    return [lo + i * step for i in range(RECENT_N)], span


def targets_history(t: float) -> tuple[list[float], float]:
    """N=37 targets evenly spaced over [0, t]."""
    if HISTORY_N == 1:
        return [t], t
    step = t / (HISTORY_N - 1)
    return [i * step for i in range(HISTORY_N)], t


def _encode(frame) -> bytes:
    img = frame.to_image()
    if img.mode != "RGB":
        img = img.convert("RGB")
    img = img.resize((OUT_W, OUT_H), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False, compress_level=6)
    return buf.getvalue()


def _frame_at(container, vs, target: float):
    """Latest decoded frame with pts <= target, via keyframe seek + forward decode."""
    tb = vs.time_base
    try:
        container.seek(max(0, int(target / tb)), stream=vs, backward=True, any_frame=False)
    except av.AVError:
        container.seek(0, stream=vs, backward=True, any_frame=False)
    prev = None
    for frame in container.decode(video=0):
        if frame.pts is None:
            continue
        ts = float(frame.pts * tb)
        if ts > target + 1e-9:
            break
        prev = frame
    if prev is not None:
        return prev, False
    # No frame has pts <= target. Only happens when the stream's first frame
    # starts after `target` (e.g. target 0.0 on a stream whose first pts is 0.033).
    # Documented fallback: the earliest frame in the stream. Still <= query time.
    container.seek(0, stream=vs, backward=True, any_frame=False)
    for frame in container.decode(video=0):
        if frame.pts is None:
            continue
        return frame, True
    return None, True


def render(path: str, mode: str, t: float | None):
    """Return (list_of_png_bytes, meta). t is the query time; None means whole video.

    meta: targets, actual frame pts, sha256 per frame, span, n_distinct, fewer_than_N flag.
    """
    if t is None:
        t_eff = duration_s(path)
        whole = True
    else:
        t_eff = float(t)
        whole = False

    if mode == "RECENT":
        targets, span = targets_recent(t_eff)
    elif mode == "HISTORY":
        targets, span = targets_history(t_eff)
    else:
        raise ValueError(mode)

    pngs: list[bytes | None] = [None] * len(targets)
    pts_used: list[float | None] = [None] * len(targets)
    fallbacks: list[bool] = [False] * len(targets)
    need = []
    for i, tg in enumerate(targets):
        hit = _cache_get((path, round(tg, 4)))
        if hit is None:
            need.append(tg)
        else:
            pngs[i], pts_used[i], fb = hit
            fallbacks[i] = fb

    if need:
        with av.open(path) as container:
            vs = container.streams.video[0]
            vs.thread_type = "AUTO"
            tb = vs.time_base
            got: dict[float, tuple[bytes, float]] = {}
            for tg in sorted(set(need)):
                fr, fallback = _frame_at(container, vs, tg)
                if fr is None:
                    raise RuntimeError(f"no frame <= {tg} in {path}")
                got[round(tg, 4)] = (_encode(fr), float(fr.pts * tb), fallback)
        for i, tg in enumerate(targets):
            if pngs[i] is None:
                k = round(tg, 4)
                _cache_put((path, k), got[k])
                pngs[i], pts_used[i], fallbacks[i] = got[k]

    shas = [hashlib.sha256(p).hexdigest() for p in pngs]
    n_distinct = len(set(shas))

    # HARD ASSERTION: no frame may come from after the query time
    limit = t_eff + 1e-6
    for tg, p, fb in zip(targets, pts_used, fallbacks):
        # HARD: never a frame from after the query time.
        assert p <= limit, f"frame pts {p} > query time {t_eff} in {path}"
        if not fb:
            assert p <= tg + 1e-6, f"frame pts {p} > its target {tg} in {path}"

    meta = {
        "mode": mode,
        "query_time_s": None if whole else t_eff,
        "whole_video": whole,
        "video_duration_s": t_eff if whole else None,
        "n_frames": len(pngs),
        "targets_s": [round(x, 4) for x in targets],
        "frame_pts_s": [round(x, 4) for x in pts_used],
        "frame_sha256": shas,
        "span_s": round(span, 4),
        "span_shorter_than_spec": bool(mode == "RECENT" and span < RECENT_SPAN_S - 1e-9),
        "n_distinct_frames": n_distinct,
        "fewer_distinct_than_N": bool(n_distinct < len(pngs)),
        "max_frame_pts_s": round(max(pts_used), 4) if pts_used else None,
        "first_frame_fallbacks": int(sum(fallbacks)),
    }
    return pngs, meta

