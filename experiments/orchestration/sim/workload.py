#!/usr/bin/env python3
"""StudySIM1c-scoped - the demand trace. CPU only; nothing here runs a model.

A cell's trace is built ONCE from a fixed seed and its sha256 is asserted identical across every
arm that runs it (fairness rule 6). Nothing in a trace depends on a policy.

What a trace contains, and where each part comes from:

  * EPISODIC STREAMS. StudyD14b's 300 validation clips (150 positive, 150 negative) and their
    committed per-grid-point scores for each arm, on StudyE9b's 0.25-s grid. The clips are dealt
    round-robin to the streams from a seeded permutation and each stream plays its own clips back
    to back, so the whole clip set is covered exactly once per run whatever the fleet size - which
    is what makes the challenge mAP of two different fleet sizes the same object.
  * CONNECTIVITY. StudyE31b's Irish 5G outage traces, as committed by StudyE6b in
    `results/orchestration/study_e6b/e6b_traces.npz`; one `outdoor_driving` trace per stream,
    chosen by the cell's seed, one bit per second, looped if the run outlasts the trace.
  * RECALL SESSIONS. S-EMBER videos with their questions at the committed question times and
    categories, read through StudyE6b's own loaders. CORRECTNESS IS NEVER SIMULATED: it is read
    from StudyB-baselines' committed per-question tables at answer time.

THE MIX AND THE FLEET LADDER. The specification gives three mixes and a fleet ladder "2-32
episodic streams x 2-32 recall sessions". Those two are read here as ONE ladder parameter F in
{2, 4, 8, 16, 32} and a mix that sets the ratio, because a full cross product would make the
three mixes redundant with the ladder's two axes:

    episodic-dominant : (F streams, max(2, F // 4) sessions)
    balanced          : (F streams, F sessions)
    recall-dominant   : (max(2, F // 4) streams, F sessions)

This reading is declared here, in the report and in the EXPERIMENTS.md row. The alternative
reading (a 5 x 5 cross product per mix) is a five-fold larger sweep and is named in the report's
compute projection.
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for p in (ROOT / "experiments/dashcam", ROOT / "experiments/orchestration/baselines",
          ROOT / "experiments/lib"):
    sys.path.insert(0, str(p))

STEP_S = 0.25                      # StudyE9b's dense grid
TICK_S = 1.0                       # decision-epoch tick; a declared harness parameter
MIXES = ("episodic-dominant", "balanced", "recall-dominant")
FLEET_LADDER = (2, 4, 8, 16, 32)
DEADLINES_S = (2.0, 5.0, 10.0)
N_SEEDS = 20

_CTX = None
_CONN = None
_QUESTIONS = None


def clip_context():
    """StudyE9b's own context: committed scores, clip metadata, folds, thresholds, AP engine."""
    global _CTX
    if _CTX is None:
        import study_e9b_dense as B
        _CTX = B.build(step=STEP_S)
    return _CTX


def connectivity_traces() -> List[np.ndarray]:
    """StudyE31b's outdoor-driving connectivity, 1 bit per second, as StudyE6b committed it."""
    global _CONN
    if _CONN is None:
        z = np.load(ROOT / "results/orchestration/study_e6b/e6b_traces.npz")
        _CONN = [np.asarray(z[k], dtype=np.int8) for k in sorted(z.files)
                 if k.startswith("outdoor_driving|")]
    return _CONN


def questions():
    """Committed S-EMBER questions: video, question time, category.

    Read from StudyR1's committed inputs manifest - the SAME file StudyE6b's loader reads
    (`study_e6b_mobility.load`, line 121) and the same RECENT construction - rather than through
    that loader, because it imports scikit-learn at module level and the CPU environment on this
    host has no working scikit-learn. The fields are taken verbatim; nothing is recomputed.
    """
    global _QUESTIONS
    if _QUESTIONS is None:
        import gzip
        man = ROOT / "results/sember/study_r1/study_r1_inputs_manifest.jsonl.gz"
        byv: Dict[str, List[Tuple[float, str, str]]] = {}
        seen = set()
        for line in gzip.open(man, "rt"):
            r = json.loads(line)
            if r.get("construction") != "RECENT":
                continue
            qid = r["question_id"]
            if qid in seen:
                continue
            seen.add(qid)
            byv.setdefault(r["video_id"], []).append(
                (float(r["question_time"]), r["question_category"], qid))
        assert len(seen) == 845, len(seen)
        for v in byv:
            byv[v].sort()
        _QUESTIONS = byv
    return _QUESTIONS


# ================================================================ the trace
@dataclass
class StreamPlan:
    stream_id: str
    clips: Tuple[str, ...]            # played back to back, in this order
    starts_s: Tuple[float, ...]       # wall time at which each clip's grid index 0 occurs
    length_s: float
    conn: np.ndarray                  # 1 bit per second, StudyE31b


@dataclass
class SessionPlan:
    session_id: str
    video_id: str
    start_s: float
    tokens: int                        # D2 history size at the end of the run
    questions: Tuple[Tuple[float, str, str], ...]   # (wall time, category, question id)


@dataclass
class Trace:
    mix: str
    fleet: int
    n_streams: int
    n_sessions: int
    deadline_s: float
    seed: int
    length_s: float
    streams: Tuple[StreamPlan, ...]
    sessions: Tuple[SessionPlan, ...]
    digest: str


D2_TOKENS_PER_S = 45.0                 # StudyRH4 D2: 90 tokens per 2-s frame
D2_MAX_TOKENS = 11050                  # StudyRH5's "11k" size


def fleet_shape(mix: str, F: int) -> Tuple[int, int]:
    if mix == "episodic-dominant":
        return F, max(2, F // 4)
    if mix == "balanced":
        return F, F
    if mix == "recall-dominant":
        return max(2, F // 4), F
    raise ValueError(f"unknown mix {mix!r}")


def build_trace(mix: str, F: int, deadline_s: float, seed: int) -> Trace:
    ctx = clip_context()
    clips, meta = ctx["clips"], ctx["meta"]
    n_streams, n_sessions = fleet_shape(mix, F)
    rng = np.random.default_rng([seed, F, int(deadline_s * 10), MIXES.index(mix)])

    order = list(rng.permutation(np.asarray(clips, dtype=object)))
    deal: List[List[str]] = [[] for _ in range(n_streams)]
    for i, c in enumerate(order):
        deal[i % n_streams].append(str(c))

    conn_all = connectivity_traces()
    streams = []
    for s, cl in enumerate(deal):
        starts, t = [], 0.0
        for c in cl:
            starts.append(t)
            t += meta[c]["G"] * STEP_S
        streams.append(StreamPlan(stream_id=f"ep{s}", clips=tuple(cl), starts_s=tuple(starts),
                                  length_s=t,
                                  conn=conn_all[int(rng.integers(0, len(conn_all)))]))
    length_s = max(x.length_s for x in streams)

    # Recall sessions are built the same way the episodic streams are: a seeded permutation of
    # the S-EMBER videos is dealt round-robin to the sessions, and each session plays its videos
    # back to back until the run ends. A video contributes its OWN committed questions at their
    # OWN committed offsets; nothing about a question is invented. The run is as long as the
    # episodic side needs to cover all 300 clips, so the recall side is truncated there - which
    # is why the number of questions per run is roughly constant across the fleet ladder rather
    # than growing with it.
    qs = questions()
    vids = sorted(qs)
    vorder = [vids[int(i)] for i in rng.permutation(len(vids))]
    vlen = {v: max(qt for qt, _c, _q in qs[v]) + 60.0 for v in vids}   # last question + 60 s
    sessions = []
    for j in range(n_sessions):
        mine = vorder[j::n_sessions]
        start = -float(rng.integers(0, 601))       # staggered session ages, as StudyRH2's are
        rows, t = [], 0.0
        for v in mine:
            if t > length_s:
                break
            for qt, cat, qid in qs[v]:
                tt = t + qt
                if 0.0 <= tt <= length_s:
                    rows.append((round(float(tt), 3), cat, qid))
            t += vlen[v]
        sessions.append(SessionPlan(session_id=f"rc{j}", video_id=mine[0], start_s=start,
                                    tokens=int(min(D2_TOKENS_PER_S * (length_s - start),
                                                   D2_MAX_TOKENS)),
                                    questions=tuple(sorted(rows))))

    h = hashlib.sha256()
    h.update(repr((mix, F, n_streams, n_sessions, deadline_s, seed, STEP_S, TICK_S)).encode())
    for sp in streams:
        h.update(sp.stream_id.encode())
        h.update(repr(sp.clips).encode())
        h.update(np.asarray(sp.starts_s, dtype=np.float64).tobytes())
        h.update(sp.conn.tobytes())
    for sq in sessions:
        h.update(sq.session_id.encode())
        h.update(sq.video_id.encode())
        h.update(repr(sq.questions).encode())
        h.update(repr((sq.start_s, sq.tokens)).encode())
    return Trace(mix=mix, fleet=F, n_streams=n_streams, n_sessions=n_sessions,
                 deadline_s=deadline_s, seed=seed, length_s=length_s,
                 streams=tuple(streams), sessions=tuple(sessions),
                 digest=h.hexdigest()[:16])


def connected(sp: StreamPlan, t_s: float) -> bool:
    """StudyE31b's bit for this stream at wall time t, looping the trace if the run outlasts it."""
    return bool(sp.conn[int(t_s) % len(sp.conn)])


if __name__ == "__main__":
    for mix in MIXES:
        for F in FLEET_LADDER:
            tr = build_trace(mix, F, 5.0, 0)
            print("%-18s F=%-3d streams=%-3d sessions=%-3d length=%7.1f s questions=%-5d %s"
                  % (mix, F, tr.n_streams, tr.n_sessions, tr.length_s,
                     sum(len(s.questions) for s in tr.sessions), tr.digest))
