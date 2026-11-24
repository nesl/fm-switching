#!/usr/bin/env python3
"""THE LINK MODEL ACTUALLY APPLIED, READ OFF THE EMULATOR AND NEVER OFF THE CONFIG (D214 item 3).

WHY THIS FILE EXISTS, AND IT IS NOT A STYLE PREFERENCE. Two separate failures in this repository
have the same shape, and both are ones a config-derived header would have reproduced:

  1. The committed main operating point was MISLABELLED for weeks ("a US median"). The numbers were
     right and the label was wrong, so every reader of a figure built on it read a typical carrier
     where the measurement was the best-performing one (StudyNET-TIER1 N3, ruling of 2026-11-23).
  2. `fleet/emulator.py`'s `link_by_device` parameter has exactly TWO production references, the
     declaration at `:245` and the write at `:291`, and NO CALLER anywhere passes it
     (StudyNET-TIER1 N1, OBSERVED). So a config field could say "per-device" while the emulator
     applies one process-wide `LinkSpec` to the whole fleet, and a header copied from the config
     would say "per-device" and be wrong in a direction nothing in the run contradicts.

So the header is derived from THE OBJECT THE EMULATOR HOLDS: `FleetEmulator.links`, the dict its
own `link()` accessor consults, and `UplinkQueue.spec`, the object `links.serialise_s` is actually
called with. `read_from_emulator` is called AFTER the run, when `links` has been populated for
every device the run touched, because `links` is lazily filled by `link()` and is EMPTY before the
first event. A pre-run read would report `model = "none"` on every cell.

IT ALSO CHECKS THAT THE TWO AGREE. The uplink arithmetic reads `UplinkQueue.spec`; the RTT terms
for pulls and answer delivery read `FleetEmulator.links` directly (`emulator.py:346`, `:349-352`).
Those are meant to be the same object, and `queue_spec_is_link_object` is that identity checked per
device rather than assumed. If a future per-device injection replaced `links[d]` after a queue had
been built, the queue would keep the old spec and the two channels would silently disagree.

NOTHING HERE READS A DECISION OR WRITES ONE. Every function takes an already-finished emulator (or
a plain mapping) and returns a dict. It is called from `run_live2_real.py` after `em.run()` has
returned.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# D214 item 3 / StudyNET-TIER1 N3 ruling of 2026-11-23. THE CORRECTED LABEL, verbatim. It is the
# best-performing US carrier (T-Mobile per Ookla H2 2025: the highest carrier median 5G upload and
# the lowest carrier latency), NOT a US median, so the committed operating point sits at the
# optimistic end of the range rather than at its centre.
MAIN_OPERATING_POINT_LABEL = (
    "uniform 13.6 Mbit/s / 44 ms uplink: best-performing US carrier's 5G median "
    "(Ookla H2 2025), close to the 12 Mbit/s Bay Area 5G median (Khan et al. 2024)"
)

# The committed D75 pair the label describes. A cell whose single applied spec matches this pair to
# the tolerance below carries the label; any other spec does NOT get it, because the label names
# one measured operating point and is not a generic description of a uniform link.
MAIN_OP_UPLINK_MBPS = 13.6
MAIN_OP_RTT_MS = 44.0
_TOL = 1e-9


def _spec_dict(spec: Any) -> Dict[str, Any]:
    """`LinkSpec.as_dict()` where it exists, else whatever attributes are there."""
    if hasattr(spec, "as_dict"):
        return dict(spec.as_dict())
    return {k: getattr(spec, k, None)
            for k in ("uplink_mbps", "rtt_ms", "downlink_mbps")}


def _key(d: Dict[str, Any]) -> tuple:
    return (d.get("uplink_mbps"), d.get("rtt_ms"), d.get("downlink_mbps"))


def read_from_emulator(em: Any) -> Dict[str, Any]:
    """The applied link model, read off `em.links` and `em.queues[*].spec`. Call AFTER the run."""
    links: Dict[str, Any] = dict(getattr(em, "links", {}) or {})
    queues: Dict[str, Any] = dict(getattr(em, "queues", {}) or {})

    per_device: Dict[str, Dict[str, Any]] = {d: _spec_dict(s) for d, s in sorted(links.items())}
    distinct: List[tuple] = sorted(set(_key(v) for v in per_device.values()))

    # The queue's spec is the object the uplink serialisation arithmetic was actually called with.
    q_specs = {d: _spec_dict(q.spec) for d, q in sorted(queues.items()) if hasattr(q, "spec")}
    same_object = {d: bool(getattr(queues[d], "spec", None) is links.get(d))
                   for d in sorted(q_specs)}
    disagreeing = sorted(d for d, v in q_specs.items()
                         if d in per_device and _key(v) != _key(per_device[d]))

    if not per_device:
        model = "none"
        model_note = ("NO LINK WAS APPLIED TO ANY DEVICE: `FleetEmulator.links` is empty after the "
                      "run, so no device uploaded anything and no link arithmetic ran. On a normal "
                      "cell this means the header was read BEFORE the run, which is a bug in the "
                      "caller, not a finding about the link.")
    elif len(distinct) == 1:
        model = "uniform"
        model_note = ("ONE `LinkSpec` applied to every device that uploaded, read back off the "
                      "emulator. This is the round-1 D75 condition and it is uniform BY "
                      "CONSTRUCTION, not by configuration: `link_by_device` has no caller.")
    else:
        model = "per-device"
        model_note = ("%d DISTINCT specs were applied across %d devices, so this cell is NOT the "
                      "uniform condition. A per-device cell can only arise from a caller passing "
                      "`link_by_device`, which no committed runner does, so this header is the "
                      "evidence that an injection point was added." % (len(distinct),
                                                                       len(per_device)))

    uniform_spec = per_device[sorted(per_device)[0]] if model == "uniform" else None
    is_main_op = bool(
        uniform_spec is not None
        and uniform_spec.get("uplink_mbps") is not None
        and abs(float(uniform_spec["uplink_mbps"]) - MAIN_OP_UPLINK_MBPS) < _TOL
        and uniform_spec.get("rtt_ms") is not None
        and abs(float(uniform_spec["rtt_ms"]) - MAIN_OP_RTT_MS) < _TOL)

    out: Dict[str, Any] = {
        "_source": ("READ OFF THE EMULATOR OBJECT after the run: FleetEmulator.links (the dict "
                    "its own link() accessor consults) and UplinkQueue.spec (the object "
                    "links.serialise_s is called with). NOT read from the config, the CLI flags "
                    "or the header, because a config field can say per-device while the emulator "
                    "applies one process-wide LinkSpec (StudyNET-TIER1 N1)."),
        "link_model_applied": model,
        "link_model_note": model_note,
        "n_devices_with_an_applied_link": len(per_device),
        "n_distinct_specs_applied": len(distinct),
        "distinct_specs_applied": [dict(uplink_mbps=u, rtt_ms=r, downlink_mbps=dn)
                                   for (u, r, dn) in distinct],
        "uniform_spec_applied": uniform_spec,
        "per_device_specs_applied": per_device,
        "n_uplink_queues_built": len(q_specs),
        "queue_spec_is_link_object": same_object,
        "queue_spec_is_link_object_all": bool(same_object) and all(same_object.values()),
        "devices_where_queue_spec_disagrees_with_link": disagreeing,
        "is_committed_main_operating_point": is_main_op,
        # The corrected label is carried ONLY where the uniform condition it names actually holds.
        "main_operating_point_label": (MAIN_OPERATING_POINT_LABEL if is_main_op else None),
        "main_operating_point_label_note": (
            "Carried because the single applied spec is the committed 13.6 Mbit/s / 44 ms pair."
            if is_main_op else
            "NOT carried: this cell's applied link is not the committed 13.6 / 44 pair, so the "
            "corrected main-operating-point label would be the wrong label for it."),
        "downlink_register": ("ASSUMPTION, NOT A MEASUREMENT: no committed downlink rate exists "
                              "in this repository (fleet/links.py module docstring). The answer "
                              "payload is a few hundred bytes, so this term is about 0.2 ms "
                              "against 22 ms of RTT/2."),
        "link_by_device_injection": {
            "_register": "OBSERVED at origin 10dae57ddc6e32acaa4599bba2aa597237119ddb",
            "note": ("`link_by_device` is declared at fleet/emulator.py:245 and written at :291 "
                     "and has NO CALLER in experiments/: there is no --uplink, --rtt or --link "
                     "flag on any runner. A fleet is therefore uniform by construction. "
                     "StudyNET-TIER1 N1 classifies the per-device mechanism ABSENT under "
                     "CLAUDE.md Rule 2 (unexercised), not broken."),
        },
    }
    return out


def read_from_mapping(specs: Dict[str, Any]) -> Dict[str, Any]:
    """The same header from a bare {device_id: LinkSpec} mapping, for tests and probes."""
    class _Shim:
        links = specs
        queues: Dict[str, Any] = {}
    return read_from_emulator(_Shim())


def summary_line(hdr: Dict[str, Any]) -> str:
    """One human line for a console or a report table."""
    m = hdr.get("link_model_applied")
    if m == "none":
        return "link model applied: NONE (no device uploaded)"
    if m == "uniform":
        s = hdr.get("uniform_spec_applied") or {}
        lab = hdr.get("main_operating_point_label")
        return ("link model applied: UNIFORM %s Mbit/s uplink / %s ms RTT / %s Mbit/s downlink"
                % (s.get("uplink_mbps"), s.get("rtt_ms"), s.get("downlink_mbps"))
                + ("  [%s]" % lab if lab else ""))
    return ("link model applied: PER-DEVICE, %d distinct specs over %d devices"
            % (hdr.get("n_distinct_specs_applied") or 0,
               hdr.get("n_devices_with_an_applied_link") or 0))
