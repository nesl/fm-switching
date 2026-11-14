#!/usr/bin/env python3
"""StudyLIVE1-port, part 1: which arms can run LIVE, and which cannot. CPU only.

THE TEST, as the study's row states it:

  ORCHESTRATOR-LEVEL  the arm decides routing, admission, deferral, rate or cadence, recall
                      placement, or session retention. A process outside the serving engine can
                      enact all of that through the vLLM OpenAI API (which request to send, when
                      to send it, how to chunk it, what to put in it) plus the existing host
                      tier. These arms run live.
  ENGINE-LEVEL        the arm's mechanism lives INSIDE the serving engine: scheduler internals,
                      KV layout, or its own cache layer under the engine. No orchestrator can
                      enact it; it stays simulator-only, or is represented by a SERVER
                      CONFIGURATION where vLLM 0.31.0 already implements the same thing.

The classification is per arm and each carries its reason. Nothing here runs a model.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / "experiments/orchestration/baselines/registry.yaml"

ORCH = "ORCHESTRATOR-LEVEL"
ENG = "ENGINE-LEVEL"
CFG = "SERVER CONFIGURATION"
NB = "NOT BUILT"

# arm -> (class, reason). The arm names are the registry's.
CLASS: Dict[str, tuple] = {
    "device-only": (ORCH, "it decides routing only: every episodic call and every recall stays "
                          "on the device, so the orchestrator simply sends nothing to the "
                          "server. It is the floor of the live comparison."),
    "always-cloud-fcfs": (ORCH, "every call goes to the server in arrival order, which is what "
                                "the orchestrator does by default. It is the live reference."),
    "random-admission": (ORCH, "admission only, 20 seeds; the orchestrator draws and sends or "
                               "does not send."),
    "round-robin": (ORCH, "an equal cloud share per stream is a sending decision."),
    "static-partition": (ORCH, "a fixed cloud share per query class is a sending decision."),
    "edf-service-time": (ORCH, "admission by a service-time estimate with EDF order: the "
                               "orchestrator holds its own queue and submits in its own order."),
    "hindsight-oracle": (ORCH + " (EXCLUDED)", "it is enactable, but it reads the future "
                                               "(`reads_future = True`), so it is an upper bound "
                                               "and is excluded from every deployable live "
                                               "comparison, exactly as in the simulator."),
    "videostorm": (ORCH, "rate allocation across streams: cadence and frame count per stream are "
                         "what the orchestrator puts in the request and how often it sends it."),
    "ekya": (ORCH, "resource allocation across streams plus session demotion; both are sending "
                   "and retention decisions."),
    "tuned-engine": (CFG, "it IS an engine configuration (StudyE10e's P1 flags). Live, it is not "
                          "a policy at all: it is the server the cell is started with, and it "
                          "may be run only as a config arm with every other arm held at E0."),
    "clockwork": (ORCH, "admission from a predicted load time. The prediction reads the live "
                        "TTFT history the harness already records; the decision is whether to "
                        "send."),
    "confidence-cascade": (ORCH, "device first, escalate on low confidence: the orchestrator "
                                 "runs the device answer and decides whether to send a cloud "
                                 "request."),
    "inar-vl": (ORCH, "joint routing, cadence and frame count per stream."),
    "hybrid-llm": (ORCH, "a query router: it decides device or cloud per episodic stream."),
    "routellm": (ORCH, "a query router, as above."),
    "perllm": (ORCH, "joint routing and rate selection under an SLO."),
    "attentionstore": (ENG, "AttentionStore IS a host-side KV cache hierarchy with its own "
                            "lookup, placement and prefetch inside the engine. An orchestrator "
                            "can move a SESSION between tiers but cannot implement a cache "
                            "layer under vLLM's attention, so what would run live is not "
                            "AttentionStore."),
    "lmcache": (CFG, "LMCache is a CPU / disk KV cache layer under the engine. vLLM 0.31.0's "
                     "native OffloadingConnector (`--kv-offloading-backend native "
                     "--kv-offloading-size 256`, the KV-HOST configuration this suite already "
                     "measures) is the same kind of thing, so live it is represented by that "
                     "SERVER CONFIGURATION and never by a policy. Any claim is about vLLM's "
                     "native offload, not about LMCache."),
    "pensieve": (ENG, "its mechanism is MULTI-TIER PARTIAL RESIDENCY inside the KV manager - "
                      "part of a session's cache resident, part not. The API exposes no partial "
                      "residency, so only whole-session placement could be enacted, which is "
                      "the mechanism removed rather than adapted."),
    "rh8-demand-aware": (ORCH, "which sessions are kept warm, from demand. Keeping a session "
                               "warm is an orchestrator action (hold it on the GPU, push it to "
                               "the host tier, or drop it)."),
    "r3-streaming": (ORCH, "remember / respond / reason: representation choice, deferral and "
                           "escalation are all sending decisions."),
    "eco-llm": (ORCH, "joint tier, representation, cadence and frame-count selection under "
                      "SLOs."),
    "streamscout": (ORCH, "a recall-side cascade over increasingly deep views: each stage is a "
                          "different request the orchestrator may or may not send."),
    "preble": (ORCH, "cache-affinity-aware admission and ORDER. The orchestrator holds the "
                     "queue and chooses what to submit next; LIMITATION, declared: once "
                     "submitted, vLLM's own scheduler controls execution order, so the arm "
                     "controls submission order and not engine order."),
    "mooncake": (ORCH, "same as preble: prefix-affinity ordering of its own submissions. The "
                       "paper's disaggregated prefill / decode architecture is NOT reproduced "
                       "and no claim is made about it."),
    "kvflow": (ORCH, "reuse-aware eviction and prefetch of SESSIONS: push to the host tier, hold "
                     "on the GPU, or rebuild. All three are orchestrator actions here."),
    "uniscale": (ORCH, "it scales the per-stream configuration, which is a sending decision."),
    "thinking-qwenvl-atdm": (ORCH, "response timing: when to answer and when to defer."),
    "simplestream": (ORCH, "a fixed recent window fed to the model: the window is what the "
                           "orchestrator puts in the request."),
    "covstream": (ORCH, "an edge / cloud split of where the session state lives, plus a heavy "
                        "model on query only. Both are orchestrator decisions."),
    "B3-best-static": (ORCH, "a static configuration choice."),
    "B4-query-type-routing": (ORCH, "routing by query type."),
    "B6-latency-aware-routing": (ORCH, "routing from the measured latency estimate, which is "
                                       "live state the harness records."),
    "B7-edf-feasibility": (ORCH, "EDF feasibility admission."),
    "B8-utility-per-gpu-second": (ORCH, "utility-per-GPU-second admission."),
    "B9-best-of-breed": (ORCH, "all four components are orchestrator-level, and live it runs "
                               "FULL - with the real host tier - rather than as the no-host "
                               "variant the simulator had to use."),
    "B10-blocking-aware-admission": (ORCH, "it is StudySLICE1's P2, which the live harness "
                                           "already runs: hold the cold build while an episodic "
                                           "call is due, release on a gap or on slack."),
    "B11-naive-slicing": (ORCH, "it is StudySLICE1's P3_2048, which the live harness already "
                                "runs: the orchestrator chunks the build into prefix-chained "
                                "requests. Live it CAN align each link, which the simulator's "
                                "1-s decision epoch could not."),
}
NOT_BUILT = {
    "flashback": "decided, not built",
    "tmo": "decided, not built",
    "route2look": "dropped (unverified)",
    "fairway": "dropped (unverified)",
    "querystream": "verified, not built (mechanism not fully specified)",
    "covstream-PRE-ADDENDUM-SUPERSEDED": "superseded by the addendum entry",
}


def registry_names() -> List[str]:
    out, txt = [], REGISTRY.read_text()
    for m in re.finditer(r'^\s*-\s+name:\s*"([^"]+)"', txt, re.M):
        out.append(m.group(1))
    return out


def classify() -> Dict[str, object]:
    names = registry_names()
    rows, missing = [], []
    for n in names:
        if n in NOT_BUILT:
            rows.append(dict(arm=n, level=NB, reason=NOT_BUILT[n], runs_live=False))
            continue
        if n not in CLASS:
            missing.append(n)
            continue
        lvl, why = CLASS[n]
        rows.append(dict(arm=n, level=lvl, reason=why,
                         runs_live=lvl.startswith(ORCH) and "EXCLUDED" not in lvl))
    assert not missing, f"unclassified registry arms: {missing}"
    return dict(
        rule=dict(orchestrator=("decides routing, admission, deferral, rate or cadence, recall "
                                "placement or session retention, all enactable through the vLLM "
                                "OpenAI API and the existing host tier"),
                  engine=("the mechanism lives inside the serving engine: scheduler internals, "
                          "KV layout, or its own cache layer")),
        n_arms=len(rows),
        n_orchestrator=sum(1 for r in rows if r["level"].startswith(ORCH)),
        n_engine=sum(1 for r in rows if r["level"] == ENG),
        n_server_config=sum(1 for r in rows if r["level"] == CFG),
        n_not_built=sum(1 for r in rows if r["level"] == NB),
        n_runs_live=sum(1 for r in rows if r["runs_live"]),
        arms=rows)


if __name__ == "__main__":
    print(json.dumps(classify(), indent=1))
