#!/usr/bin/env python3
"""The arm-side READ SITE of `Observation.device_links` (link_events switch, default OFF).

A field written and never read is ABSENT by this project's rule. Until a sync arm exists, this is
the one named consumer: an arm built with `link_read=True` runs `read_links` on every epoch,
BEFORE its own decision, and counts what the field says. It changes no decision, by
construction: it only reads `obs`, appends to counters on the arm, and then calls the arm's own
`decide` unchanged. Step 2b expects a decision diff of ZERO against the same arm without it, and
`link_counters` being non-zero in an outage cell is what shows the field reached the arm.

Arm-scoped INSTANCE attribute, class-level ON raises (the shape of every other arm switch).
"""
from __future__ import annotations

from typing import Any, Dict

LINK_READ_SWITCH = "live2_link_read"


class LinkReadSwitchError(RuntimeError):
    pass


def arm_enables(arm: Any) -> bool:
    own = vars(arm)
    if LINK_READ_SWITCH not in own:
        for klass in type(arm).__mro__:
            if bool(klass.__dict__.get(LINK_READ_SWITCH, False)):
                raise LinkReadSwitchError("%s is ON as a CLASS attribute of %s"
                                          % (LINK_READ_SWITCH, klass.__name__))
    v = own.get(LINK_READ_SWITCH, False)
    if not isinstance(v, bool):
        raise LinkReadSwitchError("%s must be a bool" % LINK_READ_SWITCH)
    return v


def new_counters() -> Dict[str, Any]:
    return dict(link_epochs_read=0, link_epochs_with_records=0, link_offline_epochs=0,
                link_reconnects_seen=0, link_backlog_frames_seen=0, link_backlog_tokens_seen=0,
                link_first_events=[], _last={})


def read_links(arm: Any, obs: Any) -> None:
    """THE READ SITE. Called once per epoch from the wrapped `decide`."""
    c = arm.link_counters
    c["link_epochs_read"] += 1
    links = obs.device_links
    if links:
        c["link_epochs_with_records"] += 1
    if any(not lk.connected for lk in links):
        c["link_offline_epochs"] += 1
    last = c["_last"]
    for lk in links:
        key = (lk.connected, lk.offline_since, lk.back_online_at)
        if last.get(lk.device_id, (True, None, None)) == key:
            continue
        last[lk.device_id] = key
        if lk.connected and lk.back_online_at is not None:
            c["link_reconnects_seen"] += 1
            c["link_backlog_frames_seen"] += lk.backlog_frames
            c["link_backlog_tokens_seen"] += lk.backlog_tokens
        if len(c["link_first_events"]) < 40:
            c["link_first_events"].append(dict(
                now_s=obs.now_s, epoch=obs.epoch, device_id=lk.device_id, connected=lk.connected,
                offline_since=lk.offline_since, back_online_at=lk.back_online_at,
                backlog_frames=lk.backlog_frames, backlog_tokens=lk.backlog_tokens))


def install(arm: Any) -> None:
    """Turn the read on for THIS INSTANCE and wrap `decide` (the decision is the arm's own)."""
    object.__setattr__(arm, LINK_READ_SWITCH, True)
    arm.link_counters = new_counters()
    inner = arm.decide

    def decide(obs):
        read_links(arm, obs)
        return inner(obs)
    arm.decide = decide
    if not arm_enables(arm):                                               # pragma: no cover
        raise LinkReadSwitchError("link read did not take on the instance")
