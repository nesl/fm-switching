#!/usr/bin/env python3
"""StudyCOVEX-harden 1a: the BLIND-SPOT audit.

For every value channel in DeltaJ crossed with every candidate kind, the fraction of candidates
where that channel's contribution is EXACTLY zero, and the fraction where the whole DeltaJ ties
at zero. A channel that is always zero for a kind where it should matter is a blind spot: the
policy cannot see that consideration at all, however large it is.
"""
from __future__ import annotations

import collections
from typing import Any, Dict, List

from _harness import CHANNELS, channel_identity_error

EPS = 1e-12


def summarise(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_kind: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    for r in records:
        by_kind[r["kind"]].append(r)

    errs = [e for e in (channel_identity_error(r) for r in records) if e is not None]
    out: Dict[str, Any] = dict(
        n_candidates=len(records),
        decomposition_check=dict(
            n_checked=len(errs), max_abs_error=(max(errs) if errs else None),
            identity="delta_j == sh_own + sh_harm + rc_util + z + cont + sv + backlog",
            holds=bool(errs and max(errs) < 1e-9)),
        by_kind={})
    for kind, rs in sorted(by_kind.items()):
        n = len(rs)
        chan = {}
        for c in CHANNELS:
            vals = [r.get(c) for r in rs if r.get(c) is not None]
            if not vals:
                chan[c] = dict(n=0, exactly_zero_frac=None)
                continue
            nz = sum(1 for v in vals if abs(v) <= EPS)
            pos = sum(1 for v in vals if v > EPS)
            neg = sum(1 for v in vals if v < -EPS)
            chan[c] = dict(n=len(vals), exactly_zero_frac=round(nz / len(vals), 4),
                           positive=pos, negative=neg,
                           min=round(min(vals), 6), max=round(max(vals), 6),
                           mean=round(sum(vals) / len(vals), 6))
        dj = [r["delta_j"] for r in rs]
        out["by_kind"][kind] = dict(
            n=n,
            delta_j_exactly_zero_frac=round(sum(1 for v in dj if abs(v) <= EPS) / n, 4),
            delta_j_le_zero_frac=round(sum(1 for v in dj if v <= EPS) / n, 4),
            delta_j_positive=sum(1 for v in dj if v > EPS),
            delta_j_min=round(min(dj), 6), delta_j_max=round(max(dj), 6),
            channels=chan)
    return out


def blind_spots(summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    """A channel is flagged when it is exactly zero in at least 99 percent of a kind's
    candidates. The 99 percent bar is stated here rather than tuned: it separates "structurally
    absent" from "usually small"."""
    flags = []
    SHOULD_MATTER = {
        "recall_admit": ("rc_util_delta", "z", "cont_delta"),
        "piece_release": ("rc_util_delta", "z", "cont_delta"),
        "piece_defer": ("rc_util_delta", "z", "cont_delta"),
        "state_promote_rebuild": ("rc_util_delta", "z", "cont_delta"),
        "state_materialize": ("rc_util_delta", "cont_delta"),
        "sh_admit": ("sh_own_delta", "z"),
        "sh_dispatch": ("sh_own_delta", "z"),
        "sh_release": ("sh_own_delta", "z"),
        "sh_hold": ("sh_own_delta", "z"),
    }
    for kind, d in summary.get("by_kind", {}).items():
        for c, cd in d["channels"].items():
            f = cd.get("exactly_zero_frac")
            if f is None or f < 0.99:
                continue
            flags.append(dict(kind=kind, channel=c, exactly_zero_frac=f, n=cd["n"],
                              should_matter=bool(c in SHOULD_MATTER.get(kind, ())),
                              severity=("HIGH" if c in SHOULD_MATTER.get(kind, ()) else "note")))
    flags.sort(key=lambda x: (x["severity"] != "HIGH", x["kind"], x["channel"]))
    return flags
