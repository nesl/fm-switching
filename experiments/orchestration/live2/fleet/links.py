#!/usr/bin/env python3
"""The emulated access link of one device: uplink serialisation, RTT and downlink.

StudyLIVE2-fleet, part 4. CPU only; no network is touched. This module is pure arithmetic so
that the timing rules can be unit-tested away from the real-time loop.

COMMITTED CONSTANTS (design decision D75, uniform over the fleet in round 1):

  uplink   13.6 Mbit/s   the committed uplink of StudyE4, StudyE9/E9b and StudyCTRL1/1b/1c
                         ("uplink 13.6 Mbit/s, RTT 0.044 s"), fixed, no variability, no outages
  rtt      44 ms         the same committed pair

  downlink 13.6 Mbit/s   ASSUMPTION, NOT A MEASUREMENT. No committed downlink rate exists in
                         this repository: the committed cloud-latency convention (StudyE9
                         section: "RTT 0.044 s + 354,902 B at 13.6 Mbit/s + TTFT") charges the
                         UPLOAD only and omits the answer payload entirely. Round 1 extends that
                         constant symmetrically so the answer payload is charged rather than
                         ignored. A cloud answer here is a few hundred bytes, so this term is
                         about 0.2 ms against the 22 ms of RTT/2 and the choice of downlink rate
                         cannot change any outcome; `downlink_sensitivity_s` makes that explicit.

TIMING RULES (D75, as written in the round-1 interface):

  upload delay   = bytes * 8 / uplink + RTT / 2          (serialisation then one-way flight)
  pull message   = RTT / 2                                (mode B: coordinator -> device)
  answer deliver = RTT / 2 + payload_bytes / downlink     (cloud -> application)

ONE UPLINK PER DEVICE, SHARED SERIALLY. A device has a single uplink. Monitoring frames and
history batches contend for it FIFO in the order they are offered: a transfer starts at
max(offer_time, uplink_free_at) and the queueing delay it suffered is recorded, never hidden
inside the transfer time. `UplinkQueue` is that bookkeeping.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

UPLINK_MBPS = 13.6          # D75, committed (StudyE4 / E9 / CTRL1c)
RTT_MS = 44.0               # D75, committed (same pair)
DOWNLINK_MBPS = 13.6        # ASSUMPTION, see the module docstring

_MBIT = 1_000_000.0         # Mbit/s is decimal megabits, as in the committed arithmetic


def upload_s(nbytes: int, uplink_mbps: float = UPLINK_MBPS, rtt_ms: float = RTT_MS) -> float:
    """Serialisation of `nbytes` onto the uplink plus one-way flight (D75)."""
    if nbytes < 0:
        raise ValueError("nbytes must be non-negative")
    return nbytes * 8.0 / (uplink_mbps * _MBIT) + (rtt_ms / 1000.0) / 2.0


def serialise_s(nbytes: int, uplink_mbps: float = UPLINK_MBPS) -> float:
    """The part of `upload_s` that OCCUPIES the uplink. The flight does not occupy it."""
    return nbytes * 8.0 / (uplink_mbps * _MBIT)


def pull_s(rtt_ms: float = RTT_MS) -> float:
    """A pull_request travelling coordinator -> device (D75): one way, no payload."""
    return (rtt_ms / 1000.0) / 2.0


def deliver_s(payload_bytes: int, rtt_ms: float = RTT_MS,
              downlink_mbps: float = DOWNLINK_MBPS) -> float:
    """A cloud_answer travelling cloud -> application (D75)."""
    if payload_bytes < 0:
        raise ValueError("payload_bytes must be non-negative")
    return (rtt_ms / 1000.0) / 2.0 + payload_bytes * 8.0 / (downlink_mbps * _MBIT)


def downlink_sensitivity_s(payload_bytes: int, rates_mbps=(1.0, 5.0, 13.6, 100.0),
                           rtt_ms: float = RTT_MS) -> List[Tuple[float, float]]:
    """How much the ASSUMED downlink rate can move a delivery time, for the report."""
    return [(r, deliver_s(payload_bytes, rtt_ms, r)) for r in rates_mbps]


@dataclass
class LinkSpec:
    """One device's link. Uniform in round 1 (D75) but per-device for later rounds."""
    uplink_mbps: float = UPLINK_MBPS
    rtt_ms: float = RTT_MS
    downlink_mbps: float = DOWNLINK_MBPS

    def as_dict(self) -> dict:
        return dict(uplink_mbps=self.uplink_mbps, rtt_ms=self.rtt_ms,
                    downlink_mbps=self.downlink_mbps)


@dataclass
class UplinkTransfer:
    kind: str                 # "monitor_frame" | "history_batch"
    ref: str                  # instant_id or batch_id
    nbytes: int
    t_offer: float            # when the device wanted to send
    t_start: float            # when the uplink became free for it
    t_arrive: float           # when the last byte has landed at the coordinator
    queue_s: float            # t_start - t_offer: the delay the FIFO imposed
    cls: int = 1              # service class: 0 = question text, 1 = everything else (frames, history)

    def as_dict(self) -> dict:
        return dict(kind=self.kind, ref=self.ref, bytes=self.nbytes,
                    t_offer=round(self.t_offer, 6), t_start=round(self.t_start, 6),
                    t_arrive=round(self.t_arrive, 6), queue_s=round(self.queue_s, 6))


QUESTION_KINDS = ("recall_question",)


class UplinkQueue:
    """ONE uplink per device, shared serially FIFO between frames and history batches.

    `question_priority` (DEFAULT OFF; off, `send` is the code below unchanged and every transfer
    is class 1): a question (class 0) is served ahead of every transfer that has not started
    by its offer instant, NON-PREEMPTIVELY (a transfer already on the wire completes), FIFO by
    offer time within a class, class 0 first on a tie. The transfers it jumps are pushed back
    by its own occupancy only; `on_retime(transfer, old_t_arrive)` is called for each one moved.
    """

    def __init__(self, spec: LinkSpec, question_priority: bool = False,
                 on_retime: Optional[Callable[["UplinkTransfer", float], None]] = None) -> None:
        self.spec = spec
        self.free_at = 0.0
        self.log: List[UplinkTransfer] = []
        self.question_priority = bool(question_priority)
        self.on_retime = on_retime

    def _occ(self, tr: "UplinkTransfer") -> float:
        return serialise_s(tr.nbytes, self.spec.uplink_mbps)

    def _send_question(self, kind: str, ref: str, nbytes: int, t_offer: float) -> UplinkTransfer:
        log = self.log
        i = len(log)
        while i > 0 and log[i - 1].t_start >= t_offer:
            i -= 1
        while i < len(log) and log[i].cls == 0 and log[i].t_offer <= t_offer:
            i += 1
        prev_end = log[i - 1].t_start + self._occ(log[i - 1]) if i > 0 else 0.0
        t_start = max(t_offer, prev_end)
        occupancy = serialise_s(nbytes, self.spec.uplink_mbps)
        tr = UplinkTransfer(kind=kind, ref=ref, nbytes=nbytes, t_offer=t_offer, t_start=t_start,
                            t_arrive=t_start + occupancy + (self.spec.rtt_ms / 1000.0) / 2.0,
                            queue_s=t_start - t_offer, cls=0)
        log.insert(i, tr)
        end = t_start + occupancy
        for later in log[i + 1:]:
            ns = max(later.t_offer, end)
            if ns != later.t_start:
                old = later.t_arrive
                later.t_start = ns
                later.t_arrive = ns + self._occ(later) + (self.spec.rtt_ms / 1000.0) / 2.0
                later.queue_s = ns - later.t_offer
                if self.on_retime is not None:
                    self.on_retime(later, old)
            end = later.t_start + self._occ(later)
        self.free_at = max(self.free_at, end)
        return tr

    def send(self, kind: str, ref: str, nbytes: int, t_offer: float) -> UplinkTransfer:
        if self.question_priority and kind in QUESTION_KINDS:
            return self._send_question(kind, ref, nbytes, t_offer)
        t_start = max(t_offer, self.free_at)
        occupancy = serialise_s(nbytes, self.spec.uplink_mbps)
        self.free_at = t_start + occupancy
        tr = UplinkTransfer(kind=kind, ref=ref, nbytes=nbytes, t_offer=t_offer, t_start=t_start,
                            t_arrive=t_start + occupancy + (self.spec.rtt_ms / 1000.0) / 2.0,
                            queue_s=t_start - t_offer)
        self.log.append(tr)
        return tr

    def stats(self) -> dict:
        q = sorted(t.queue_s for t in self.log)
        if not q:
            return dict(n=0, busy_s=0.0, queue_p50=None, queue_p99=None, queue_max=None)
        return dict(n=len(q),
                    busy_s=round(sum(serialise_s(t.nbytes, self.spec.uplink_mbps)
                                     for t in self.log), 6),
                    queue_p50=round(q[len(q) // 2], 6),
                    queue_p99=round(q[min(len(q) - 1, int(0.99 * len(q)))], 6),
                    queue_max=round(q[-1], 6))
