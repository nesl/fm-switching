#!/usr/bin/env python3
"""FAITHFUL RECONSTRUCTION of CoVStream's edge-cloud split (arXiv:2606.22804).

Paper: X. Liu, G. Chen, Z. Yan, K. Wu, W. Wang, "CoVStream: Edge-Cloud Collaboration for
Understanding of Long Video Streams", arXiv:2606.22804. No official or author-endorsed code
release was found.

Mapping to the paper:
  "The edge node converts raw streams into compact visual features and semantic captions. The
  cloud server organizes this data into an entity graph and global visual context, and runs the
  heavy reasoning model ONLY WHEN A USER QUERY ARRIVES." Reported: 87.6 % bandwidth reduction
  while retaining 99.2 % of the cloud baseline's accuracy on LVBench.

  edge_encode()     the edge's continuous work: compress each frame to features plus a caption,
                    at a per-frame cost and a per-frame byte size. This runs whether or not a
                    query ever arrives, which is the paper's bandwidth argument AND its standing
                    cost.
  cloud_ingest()    the cloud's continuous work: fold each arriving packet into the entity graph
                    and global context, at a per-packet cost.
  answer()          on a query, run the heavy model over the maintained structure. No history is
                    uploaded at query time, which is where the bandwidth saving comes from.
  bandwidth_ratio() the paper's headline quantity: bytes sent by this pipeline against bytes sent
                    by uploading raw frames.

**THE CONSTRUCTION COST IS CHARGED, which the first pass of this suite did not do.** The addendum
requires it, and it is the reason CoVStream can now be built at all: its saving is paid for by
continuous edge captioning and continuous cloud graph maintenance, and a baseline that ignored
those costs would be unfair to every other policy under fairness rule 3.

NOT reconstructed, and why: the captioner and the entity-graph builder themselves (both need
inference); the retrieval over the graph. The adapted version therefore substitutes our nearest
MEASURED representation and charges a construction cost per frame - stated in the card as the
largest substitution in this suite.

CPU only; no GPU, no inference.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence


@dataclass
class EdgePacket:
    frame_index: int
    feature_bytes: int
    caption_bytes: int
    edge_cost_s: float

    @property
    def bytes_(self) -> int:
        return self.feature_bytes + self.caption_bytes


@dataclass
class CloudState:
    packets: int = 0
    graph_cost_s: float = 0.0
    bytes_received: int = 0


def edge_encode(n_frames: int, feature_bytes: int, caption_bytes: int,
                edge_cost_s_per_frame: float) -> List[EdgePacket]:
    """The edge's standing work, independent of whether a query arrives."""
    return [EdgePacket(i, feature_bytes, caption_bytes, edge_cost_s_per_frame)
            for i in range(int(n_frames))]


def cloud_ingest(packets: Sequence[EdgePacket], graph_cost_s_per_packet: float) -> CloudState:
    """The cloud's standing work: maintain the entity graph and global context."""
    st = CloudState()
    for p in packets:
        st.packets += 1
        st.bytes_received += p.bytes_
        st.graph_cost_s += graph_cost_s_per_packet
    return st


def answer_cost_s(state: CloudState, heavy_model_s: float) -> float:
    """On a query the heavy model runs over the maintained structure; nothing is uploaded now."""
    return float(heavy_model_s)


def bandwidth_ratio(state: CloudState, raw_bytes_if_uploaded: int) -> float:
    """Bytes this pipeline sent, over bytes raw-frame upload would have sent."""
    if raw_bytes_if_uploaded <= 0:
        return 0.0
    return state.bytes_received / float(raw_bytes_if_uploaded)


def standing_cost_s(packets: Sequence[EdgePacket], state: CloudState) -> float:
    """Total construction compute: edge encoding plus cloud graph maintenance. CHARGED."""
    return sum(p.edge_cost_s for p in packets) + state.graph_cost_s
