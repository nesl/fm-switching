#!/usr/bin/env python3
"""Drive the live2 coordinator from the fleet emulator. CPU only.

WHY THIS EXISTS. There are two loop owners. `live2/coordinator.py::Live2Coordinator.run()` owns
its own clock and consumes a static event list, which is what the flash tests and a replay need.
`live2/fleet/emulator.py::FleetEmulator` owns the clock for a LIVE run and calls into a
coordinator through its own Protocol (`fleet/emulator.py:76-78`):

    on_event(event, t) -> Sequence[reply]
    tick(t)            -> Sequence[reply]

`EmulatorBridge` exposes the live2 coordinator through exactly that Protocol, so the live run is
emulator-driven without either side changing: the bridge ingests the wire event, runs one
decision epoch at the emulator's `t`, and returns whatever the coordinator produced for the
fleet (`pull_request` and `cloud_answer` events, in the order they were produced).

The bridge owns NO clock of its own: every call carries the emulator's `t`, which is the one run
clock `CONTRACT.md` defines. It therefore cannot drift from the fleet.
"""
from typing import Any, Dict, List, Sequence

import schema as SC


class EmulatorBridge:
    """The live2 coordinator as the fleet emulator's `Coordinator`."""

    def __init__(self, co) -> None:
        self.co = co
        self._sent = 0
        self._pulls = 0
        self.n_events = 0
        self.n_ticks = 0
        self.n_decisions = 0
        self.n_skipped_forwarded = 0
        # D99 (1): ONE DECISION PER PERIOD, the same period for every arm, with that period's
        # events batched. The bridge enforces it on the EMULATOR's clock, so it holds whatever
        # the emulator's own tick_s is (it must be no coarser than the period, or a period would
        # pass without a decision); the old `decide_on_every_event` rule is gone, because it made
        # the decision rate a function of the event rate (open issue 10a).
        self._period = float(getattr(co, "decision_period_s", 0.1))
        self._next_decision = 0.0
        self._pending_epoch = "tick"

    # ---- the Protocol
    def on_event(self, event: Dict[str, Any], t: float) -> Sequence[Dict[str, Any]]:
        self.n_events += 1
        SC.parse(event)                      # an off-schema event fails here, not three calls on
        self.co.st.now = float(t)
        self.co._collect(float(t))
        epoch = self.co._ingest(event, float(t)) or "tick"
        if epoch != "tick":
            self._pending_epoch = epoch
        self._maybe_decide(float(t))
        self.co._expire(float(t))
        return self._drain()

    def tick(self, t: float) -> Sequence[Dict[str, Any]]:
        self.n_ticks += 1
        self.co.st.now = float(t)
        self.co._collect(float(t))
        self._maybe_decide(float(t))
        self.co._expire(float(t))
        return self._drain()

    def _maybe_decide(self, t: float) -> None:
        if t + 1e-9 < self._next_decision:
            return
        self.co._epoch(t, self._pending_epoch)
        self.n_decisions += 1
        self._pending_epoch = "tick"
        self._next_decision = round(t + self._period, 9)

    def close(self) -> None:
        if getattr(self.co, "be", None) is not None:
            self.co.be.close()
        if getattr(self.co, "logs", None) is not None:
            self.co.logs.close()

    # ---- replies
    def _drain(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if len(self.co.pulls) > self._pulls:
            out += list(self.co.pulls[self._pulls:])
            self._pulls = len(self.co.pulls)
        if len(self.co.cloud_answers) > self._sent:
            # StudyLIVE2-harness addendum: an answer the I/O layer already forwarded at stream
            # end is recorded but not sent again.
            fwd = getattr(self.co, "forwarded", None) or {}
            for ev in self.co.cloud_answers[self._sent:]:
                if (ev.get("payload") or {}).get("request_id") in fwd:
                    self.n_skipped_forwarded += 1
                else:
                    out.append(ev)
            self._sent = len(self.co.cloud_answers)
        return out

    def describe(self) -> Dict[str, Any]:
        return dict(arm=self.co.arm.name, n_events=self.n_events, n_ticks=self.n_ticks,
                    n_pulls=self._pulls, n_cloud_answers=self._sent,
                    n_decisions=self.n_decisions, decision_period_s=self._period,
                    n_forwarded_on_completion=len(getattr(self.co, "forwarded", None) or {}),
                    n_skipped_forwarded=self.n_skipped_forwarded,
                    n_forward_mismatch=getattr(self.co, "n_forward_mismatch", 0),
                    n_recall_first_token=getattr(self.co, "n_recall_first_token", 0),
                    n_recall_letter_differs=getattr(self.co, "n_recall_letter_differs", 0),
                    recall_letter_diffs=list(getattr(self.co, "recall_letter_diffs", []))[:50],
                    n_monitor_score_differs=getattr(self.co, "n_monitor_score_differs", 0))
