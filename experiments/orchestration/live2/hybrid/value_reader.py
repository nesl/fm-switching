#!/usr/bin/env python3
"""D149 value reader: send a representation only if it beats the device's own answer.

D149 (2) and D152 (2). The quantity compared is EXPECTED CORRECT ANSWERS DELIVERED, which is what
D152 made the headline:

    value(rep) = P(on time | rep) x accuracy(rep)      for each representation the cloud could send
    value(device) = accuracy(device)                   the device answers whenever the cloud does not

and the cloud sends the best representation only if its value strictly beats the device's. Nothing
is sent to be seen trying: a representation that cannot beat the answer the device already has is
worse than not sending it, because it occupies the engine and displaces another device's work.

WHAT THIS REPLACES. C3's second branch sent RECENT whenever the full history would not fit and
RECENT would, a FEASIBILITY test with no reference to whether the answer would be any good. On the
LH-REQ questions it actually fired on, those RECENT answers were right 11 percent of the time while
the device's own answer is right about 25 percent, so the fallback was converting a better answer
into a worse one and counting it as a save because it arrived on time.

THE TABLE IS DEV-FITTED (D6) and committed: `results/orchestration/live2/lh_req/lh_req_quality.json`,
fitted on the 28 DEV questions, where LH-REQ robots draw only from the 69 EVAL questions.

    cloud D2      0.250000      cloud RECENT  0.107143      device 4B-RECENT  0.107143

BANDS BY HISTORY LENGTH ARE NOT SUPPORTED BY THIS TABLE, and that is reported rather than faked.
D149 asks for the accuracy to be DEV-fitted by history-length band. The DEV split holds 28
questions, so three bands would hold about nine each, and the aggregate's own Wilson interval for
cloud RECENT is already [0.037, 0.272]. A per-band fit on nine questions would be noise given a
shape. The band interface exists here and is used if a band table is supplied; with none, the
aggregate is used and the choice is recorded in the decision's own record. P19's full S-EMBER device
sweep would make bands fittable.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

REPO = Path(__file__).resolve().parents[4]
LH_REQ_QUALITY = REPO / "results/orchestration/live2/lh_req/lh_req_quality.json"


class ValueTable:
    """Accuracy by (representation, tier), DEV-fitted, optionally by history-length band."""

    def __init__(self, path: Path = LH_REQ_QUALITY, bands: Optional[Dict] = None,
                 transform: str = "none") -> None:
        d = json.loads(Path(path).read_text())
        if d.get("_fit_split") != "DEV":
            raise ValueError("the LH-REQ quality table is not DEV-fitted (_fit_split=%r); D6 and "
                             "D143 A both require it" % (d.get("_fit_split"),))
        dev = d["per_split"]["DEV"]
        self.raw = {"D2": float(dev["cloud_D2"]["accuracy"]),
                    "RECENT": float(dev["cloud_RECENT"]["accuracy"]),
                    "device": float(dev["device_4B_RECENT"]["accuracy"])}
        self.n = int(dev["cloud_D2"]["n"])
        self.bands = bands
        self.transform = transform
        self.acc = self._apply(self.raw, transform)

    @staticmethod
    def _apply(raw: Dict[str, float], transform: str) -> Dict[str, float]:
        """D149 (4)'s acceptance test needs the table to be flattenable and invertible IN PLACE,
        so the control runs the same code path as the real thing and cannot differ from it."""
        if transform == "none":
            return dict(raw)
        if transform == "flat":
            m = sum(raw.values()) / len(raw)
            return {k: m for k in raw}
        if transform == "invert":
            hi, lo = max(raw.values()), min(raw.values())
            return {k: hi + lo - v for k, v in raw.items()}
        raise ValueError("transform %r must be none, flat or invert" % (transform,))

    def accuracy(self, rep: str, history_tokens: Optional[int] = None) -> float:
        if self.bands and history_tokens is not None:
            for lo, hi, tab in self.bands:
                if lo <= history_tokens < hi and rep in tab:
                    return float(tab[rep])
        return float(self.acc[rep])


def choose(reps: Tuple[str, ...], p_on_time: Callable[[str], float], table: ValueTable,
           history_tokens: Optional[int] = None) -> Dict[str, Any]:
    """The reader. Returns the chosen representation or None, with the arithmetic that chose it.

    `p_on_time(rep)` is the policy's own probability that a request sent with that representation
    is DELIVERED within the deadline. With a deterministic cost model it is 1 or 0, and the reader
    then reduces to "send the best representation that fits, and only if it beats the device".
    """
    dev = table.accuracy("device", history_tokens)
    scored = []
    for r in reps:
        p = float(p_on_time(r))
        scored.append(dict(representation=r, p_on_time=p,
                           accuracy=table.accuracy(r, history_tokens),
                           value=p * table.accuracy(r, history_tokens)))
    best = max(scored, key=lambda x: x["value"]) if scored else None
    send = bool(best and best["value"] > dev)
    return dict(send=send, representation=(best["representation"] if send else None),
                device_value=dev, best=best, considered=scored,
                band_used=bool(table.bands and history_tokens is not None),
                transform=table.transform,
                reason=("value %.4f beats the device's %.4f" % (best["value"], dev)) if send
                else ("no representation beats the device's own answer at %.4f" % dev))
