#!/usr/bin/env python3
"""The NDJSON + length-prefixed-blob wire shared by every StudyREAL-NET component.

Python 3.8 compatible (orin-1 and orin-2 run 3.8.10), stdlib only.

FRAMING. One line of JSON per message, UTF-8, newline-terminated. A message that carries
image bytes sets `blob_bytes` to the payload length; the raw bytes follow the newline
IMMEDIATELY, with no base64 and no framing of their own. So a monitor_frame on the wire is:

    {"kind":"monitor_frame",...,"blob_bytes":67170}\\n
    <67170 raw JPEG bytes>

WHY NOT BASE64. The point of this harness is that real payload bytes cross a real link, so
the byte count on the wire must equal `frame_bytes` in the trace. Base64 would inflate it by
4/3 and silently invalidate every transport measurement.

ONE CONNECTION PER DEVICE, HELD OPEN. Measured TCP setup on this fabric is 0.9-2.8 ms, which
is 1.5-4x a whole 59,601 B payload round trip, and `live2/fleet/links.py` models no connection
lifecycle at all. Reconnecting per frame would invent a cost the emulator never charges, so
`Wire` is built to be opened once and reused.
"""
from __future__ import annotations

import json
import socket
import struct
from typing import Any, Dict, Optional, Tuple

BLOB_KEY = "blob_bytes"
MAX_LINE = 1 << 20          # a recall_question with options is a few KB; 1 MB is generous
MAX_BLOB = 8 << 20          # the largest committed frame is 119 KB; 8 MB is generous


class WireError(Exception):
    """A framing or protocol error. Never raised for an ordinary close."""


class Wire:
    """Length-prefixed NDJSON over one socket. Not thread-safe; one Wire per connection."""

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        self._buf = bytearray()
        self.n_sent = 0
        self.n_recv = 0
        self.bytes_sent = 0
        self.bytes_recv = 0

    # ---- send
    def send(self, msg: Dict[str, Any], blob: Optional[bytes] = None) -> int:
        """Send one message, optionally with a raw payload. Returns bytes written."""
        m = dict(msg)
        if blob is not None:
            m[BLOB_KEY] = len(blob)
        line = json.dumps(m, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(line) > MAX_LINE:
            raise WireError("message line %d B exceeds MAX_LINE %d" % (len(line), MAX_LINE))
        payload = line if blob is None else line + blob
        self.sock.sendall(payload)
        self.n_sent += 1
        self.bytes_sent += len(payload)
        return len(payload)

    # ---- receive
    def _fill(self, want: int) -> None:
        """Read until the buffer holds at least `want` bytes, or the peer closes."""
        while len(self._buf) < want:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EOFError("peer closed")
            self._buf += chunk

    def _read_line(self) -> bytes:
        while True:
            i = self._buf.find(b"\n")
            if i >= 0:
                line = bytes(self._buf[:i])
                del self._buf[:i + 1]
                return line
            if len(self._buf) > MAX_LINE:
                raise WireError("no newline in %d B; MAX_LINE %d" % (len(self._buf), MAX_LINE))
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EOFError("peer closed")
            self._buf += chunk

    def recv(self) -> Tuple[Dict[str, Any], Optional[bytes]]:
        """Receive one message and its blob if it has one. Raises EOFError on clean close."""
        line = self._read_line()
        try:
            msg = json.loads(line.decode("utf-8"))
        except Exception as e:
            raise WireError("bad JSON line (%d B): %s" % (len(line), e))
        if not isinstance(msg, dict):
            raise WireError("wire message is %s, not an object" % type(msg).__name__)
        n = msg.get(BLOB_KEY)
        blob = None
        if n:
            n = int(n)
            if n < 0 or n > MAX_BLOB:
                raise WireError("blob_bytes %d outside [0, %d]" % (n, MAX_BLOB))
            self._fill(n)
            blob = bytes(self._buf[:n])
            del self._buf[:n]
        self.n_recv += 1
        self.bytes_recv += len(line) + 1 + (len(blob) if blob else 0)
        return msg, blob

    def close(self) -> None:
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass

    def stats(self) -> Dict[str, Any]:
        return dict(n_sent=self.n_sent, n_recv=self.n_recv,
                    bytes_sent=self.bytes_sent, bytes_recv=self.bytes_recv)


def connect(host: str, port: int, timeout: float = 10.0) -> Wire:
    """Open one connection. Handles zone-scoped IPv6 (orin-4 is fe80::...%ens6f0).

    getaddrinfo resolves the scope id; a bare socket(AF_INET) would refuse the address, which
    is exactly the bug that made orin-4 unreachable during the 2026-11-25 measurement.
    """
    last = None
    for fam, kind, proto, _canon, addr in socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM):
        try:
            s = socket.socket(fam, kind, proto)
            s.settimeout(timeout)
            s.connect(addr)
            return Wire(s)
        except OSError as e:
            last = e
            try:
                s.close()
            except Exception:
                pass
    raise OSError("could not connect to %s:%s (%s)" % (host, port, last))


def listener(port: int, backlog: int = 32) -> socket.socket:
    """A dual-stack listening socket: IPv4 clients and zone-scoped IPv6 both reach it."""
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except OSError:
            pass
        s.bind(("::", port))
    except OSError:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", port))
    s.listen(backlog)
    return s
