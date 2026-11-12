#!/usr/bin/env python3
"""CoVStream (arXiv:2606.22804), ADAPTED behind our policy interface. Case D. Conditional P1.

Decision logic = `reconstructed/covstream.py`, unchanged. Mapping in cards/covstream.md.

**WHY THIS IS NOW BUILT.** The first pass of this suite listed CoVStream as related work, because
its edge tier produces captions and its cloud tier maintains an entity graph, and our evidence
inventory holds only representations we have measured. The addendum promotes it to conditional P1
and requires that its **representation-construction compute be charged**, which is exactly what
made it unfair before: its 87.6 % bandwidth saving is paid for by continuous edge captioning and
continuous cloud graph maintenance. With that cost charged under fairness rule 3 the baseline is
comparable, and the remaining substitution is stated plainly:

  edge features + captions  <- our D2 representation (a strided history), the nearest MEASURED
      thing we hold. **We do not caption and we do not build an entity graph**; nothing in this
      suite has ever measured either, so this baseline is "CoVStream's edge-cloud SPLIT with our
      representations", not CoVStream. This is the largest substitution in the suite.
  cloud entity graph        <- the session's GPU/host-warm D2 state, maintained continuously
  heavy model on query only <- serve from the warm state, uploading nothing at query time
  construction compute      <- CHARGED: a per-frame edge cost and a per-packet cloud cost, both
      declared and visible in the smoke results

CPU only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent / "reconstructed"))

import costs as C
from covstream import cloud_ingest, edge_encode, standing_cost_s  # noqa: E402
from interface import (Action, Observation, Policy, RecallAction, SessionAction, StreamAction)


class CoVStreamAdapted(Policy):
    name = "covstream"
    case = "D"
    experiments = ("B-recall",)
    paper = "Liu, Chen, Yan, Wu, Wang, CoVStream: Edge-Cloud Collaboration for Understanding of Long Video Streams, arXiv:2606.22804"
    decides = ("recall_decision", "representation", "session_action", "episodic_mode")
    defaults_used = ("cadence_s", "frame_count", "order")

    def __init__(self, edge_cost_s_per_frame: float = 0.01,
                 graph_cost_s_per_packet: float = 0.002, frame_period_s: float = 1.0) -> None:
        self.edge_cost = float(edge_cost_s_per_frame)
        self.graph_cost = float(graph_cost_s_per_packet)
        self.frame_period_s = float(frame_period_s)
        self._charged_until_s = 0.0
        self.standing_cost_s_total = 0.0

    def reset(self, seed: int = 0) -> None:
        self._charged_until_s = 0.0
        self.standing_cost_s_total = 0.0

    def _charge_construction(self, now_s: float) -> float:
        """Fairness rule 3: the construction compute is charged continuously, whether or not a
        query ever arrives. Returns the cost incurred since the last epoch."""
        n = int((now_s - self._charged_until_s) / self.frame_period_s)
        if n <= 0:
            return 0.0
        pk = edge_encode(n, feature_bytes=4000, caption_bytes=400,
                         edge_cost_s_per_frame=self.edge_cost)
        st = cloud_ingest(pk, graph_cost_s_per_packet=self.graph_cost)
        c = standing_cost_s(pk, st)
        self._charged_until_s += n * self.frame_period_s
        self.standing_cost_s_total += c
        return c

    def decide(self, obs: Observation) -> Action:
        self._charge_construction(obs.now_s)
        # the heavy model runs only on a query, over the continuously maintained state
        rec: List[RecallAction] = []
        for q in obs.recall:
            have = {e.representation for e in q.evidence}
            rep = "D2" if "D2" in have else ("RICH" if "RICH" in have else "RECENT")
            rec.append(RecallAction(q.query_id, "CLOUD", representation=rep))
        known = sorted(set(obs.cloud.gpu_warm_sessions) | set(obs.cloud.host_warm_sessions)
                       | {q.session_id for q in obs.recall})
        # the cloud keeps the structure resident; that is the whole design
        return Action(
            streams=[StreamAction(s.stream_id, "local") for s in obs.streams],
            recall=rec,
            sessions=[SessionAction(s, "KEEP_GPU_WARM") for s in known[:4]]
                     + [SessionAction(s, "OFFLOAD_TO_HOST") for s in known[4:]],
            notes=dict(construction_cost_s=round(self.standing_cost_s_total, 4)))
