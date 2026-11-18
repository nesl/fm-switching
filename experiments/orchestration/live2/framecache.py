#!/usr/bin/env python3
"""Each frame's base64 data URL computed ONCE and reused. CPU only, no measurement.

StudyLIVE2-harness. The pilot's `frames_root / frame_ref` resolution read the JPEG off disk and
base64-encoded it EVERY time a frame appeared in a body (`bodies._data_url`). A robot's cold
history rebuild carries every frame it has, and a chained rebuild carries the whole prefix again
as uuid references but the NEW piece's frames as bytes, so the same file was read and encoded
many times inside one run, on the thread that owns the emulator's wall clock.

Nothing about the WIRE changes: the string this cache hands out is the string `_data_url` built,
byte for byte, which `test_live2_harness.py` asserts frame by frame. The cache only decides WHEN
the bytes are turned into base64 and how often.

Memory is the reason for the cap. 42,014 Nexar frames at a 62 KB median are 2.6 GB of JPEG and
about 3.5 GB of base64, so an unbounded cache would not fit a round-1 run. The cache is a bounded
LRU over frame_refs, sized by BYTES of base64 held, and a miss simply does the work the old path
always did.
"""
from __future__ import annotations

import base64
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Optional

JPEG_PREFIX = "data:image/jpeg;base64,"
DEFAULT_CAP_B = 1_500_000_000


class FrameCache:
    """frame_ref -> the data URL for its bytes, with a byte-capped LRU and a hit counter."""

    def __init__(self, root: Optional[Path] = None, cap_bytes: int = DEFAULT_CAP_B) -> None:
        self.root = Path(root) if root is not None else None
        self.cap_bytes = int(cap_bytes)
        self._lru: "OrderedDict[str, str]" = OrderedDict()
        self._held = 0
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0
        self.encoded_bytes = 0

    # ---- resolution
    def path_of(self, frame_ref: str) -> Optional[Path]:
        p = Path(frame_ref)
        if not p.is_absolute() and self.root is not None:
            p = self.root / frame_ref
        return p if p.exists() else None

    def data_url(self, frame_ref: str, path: Optional[Path] = None) -> Optional[str]:
        """The data URL for this frame, from the cache when it is there.

        `path` is honoured when given so a caller that already resolved the file does not resolve
        it twice; a `None` return means the frame is not on this host, exactly as before.
        """
        with self._lock:
            hit = self._lru.get(frame_ref)
            if hit is not None:
                self._lru.move_to_end(frame_ref)
                self.hits += 1
                return hit
        p = path if path is not None else self.path_of(frame_ref)
        if p is None:
            return None
        url = JPEG_PREFIX + base64.b64encode(Path(p).read_bytes()).decode()
        with self._lock:
            self.misses += 1
            self.encoded_bytes += len(url)
            if frame_ref not in self._lru:
                self._lru[frame_ref] = url
                self._held += len(url)
                while self._held > self.cap_bytes and len(self._lru) > 1:
                    _k, v = self._lru.popitem(last=False)
                    self._held -= len(v)
        return url

    def warm(self, frame_refs) -> int:
        """Encode these frames now, so no decision epoch pays for them. Returns how many."""
        n = 0
        for ref in frame_refs:
            if self.data_url(ref) is not None:
                n += 1
        return n

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return dict(n_cached=len(self._lru), held_bytes=self._held, cap_bytes=self.cap_bytes,
                        hits=self.hits, misses=self.misses, encoded_bytes=self.encoded_bytes,
                        hit_fraction=(round(self.hits / (self.hits + self.misses), 6)
                                      if (self.hits + self.misses) else None))
