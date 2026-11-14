#!/usr/bin/env python3
"""Committed service-time distributions, for the CPU test stub only. CPU only.

StudyLIVE1-port. The fake server needs a delay per request kind. It draws one from the COMMITTED
StudySLICE1 Part C rows (the E0 server, h100nvl), at the LOWEST load level of the matching
condition, and the stub then serves requests through its own single FIFO queue. Taking the
lowest-load sample makes the draw a SERVICE time rather than a queued latency, so the stub's own
queue is what produces queueing instead of it being baked into the sample twice.

**NOTHING THE STUB PRODUCES IS A MEASUREMENT.** It exists so that every ported arm can be run,
validated and traced on a machine with no GPU. Every number from a stub run is labelled as such.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[3]
PARTC = ROOT / "results/cost/study_slice1/slice1_partc_requests_h100nvl.jsonl"
LIVE = ROOT / "results/cost/study_slice1/slice1_live_requests_h100nvl.jsonl"

KIND_FIELD = {"episodic": "ttft_s", "cold_recall": "ttft_s", "recall_append": "latency_s",
              "recall_escalation": "latency_s", "recall_warmup": "latency_s"}
_DIST: Optional[Dict[str, List[float]]] = None


def _load() -> Dict[str, List[float]]:
    global _DIST
    if _DIST is not None:
        return _DIST
    by: Dict[str, Dict[float, List[float]]] = defaultdict(lambda: defaultdict(list))
    for f in (PARTC, LIVE):
        if not f.exists():
            continue
        for line in f.open():
            r = json.loads(line)
            k = r.get("kind")
            fld = KIND_FIELD.get(k)
            if fld is None or r.get(fld) is None or r.get("error"):
                continue
            if k == "episodic" and not r.get("in_window"):
                continue
            by[k][float(r.get("frac") or 0.0)].append(float(r[fld]))
    out: Dict[str, List[float]] = {}
    for k, lv in by.items():
        lo = min(lv)                      # the lowest load level present for this kind
        out[k] = sorted(lv[lo])
    _DIST = out
    return out


def sample(kind: str, rng: random.Random, tokens: int = 0) -> float:
    """A service time for one request of this kind, drawn from the committed distribution."""
    d = _load()
    v = d.get(kind) or d.get("episodic") or [0.15]
    x = v[rng.randrange(len(v))]
    if kind == "cold_recall" and tokens:
        # a sliced link is a fraction of a whole build: scale by its share of the tokens
        x *= max(min(tokens / 11050.0, 1.0), 0.02)
    return float(x)


def summary() -> Dict[str, object]:
    d = _load()
    import statistics
    return {k: dict(n=len(v), p50=round(statistics.median(v), 4), min=round(v[0], 4),
                    max=round(v[-1], 4)) for k, v in sorted(d.items())}


if __name__ == "__main__":
    print(json.dumps(dict(source=[str(PARTC), str(LIVE)], distributions=summary()), indent=1))
