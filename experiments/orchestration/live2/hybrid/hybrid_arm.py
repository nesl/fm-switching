#!/usr/bin/env python3
"""HybridArm (D138, P1): b7-edf-feasibility plus switchable components, each default OFF.

With every switch off, `decide` RETURNS b7's own decision unchanged (it calls the committed
`B7EDFFeasibility.decide`), so the base is byte-identical to b7-edf-feasibility by construction; the
proof is a decision-log diff on dry runs (tests/test_hybrid.py). b7 has NO in-flight limit: it marks
every stream for the cloud each period and admits / defers / rejects each recall by feasibility.

Components (flash code read-only: costs.py curves, b7's feasibility rule, the RC quality tables):
  C1 ordering        index = value x urgency / remaining work; urgency = 1 / max(slack, 0.1 s), slack against the
                     item's own deadline less its predicted work; work from the committed cost curve; value from
                     the committed RC tables (cloud minus device accuracy, trace-weighted) for a recall and the
                     committed SH cloud gain for a dashcam instant.
  C2 protect-fill    at risk = a recall whose slack < k_r, or a dashcam whose running on-time fraction (trailing
                     60 s) < 0.25 + m_d; at-risk work first, and (when a cap applies) one reserved slot for
                     at-risk recall; the rest in C1 order (or deadline order if C1 is off).
  C3 degradation     an at-risk recall that is infeasible as a full-history recall but feasible as RECENT is sent
                     as RECENT (the representation field is live since e924005) instead of deferred / rejected.
  C4 retention       INERT until memory pressure exists (placeholder that emits no session action).
  C5 AIMD in-flight  cap starts at 8, halves (floor 4) when the episodic latency estimate exceeds 0.8 x the
                     dashcam deadline, +1 per 5 s otherwise (ceiling 8); only the top `cap - in_flight` items are
                     released; the rest stay local (dashcam) or deferred (recall).
  C6 chooser         OFF until flash's "chooser ready" commit (policy/ choose(candidates, state)).
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
LIVE2 = HERE.parent
REPO = LIVE2.parents[2]
for p in (LIVE2, LIVE2 / "fleet", REPO / "experiments/orchestration/baselines",
          REPO / "experiments/orchestration/sim", REPO / "experiments/lib"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import costs as C                                                           # noqa: E402
from interface import Action, Observation, RecallAction, StreamAction       # noqa: E402

DASH_DEADLINE_S = 1.0
RECENT_TOKENS = 467          # live2's committed RECENT_WINDOW_TOKENS (cstate), the representation the coordinator charges


def _quality_values() -> Dict[str, float]:
    """Committed values, read-only: recall = 32B-D2 minus 4B-D2 accuracy, weighted by the EVAL category mix;
    dashcam = the committed cloud SH gain (figM1 / CTRL1b, +0.090 challenge mAP)."""
    prof = json.loads((REPO / "results/orchestration/prof1/profiles_dev.json").read_text())["RC"]["tables"]
    cl, dv = prof["32B-D2"]["by_category"], prof["4B-D2"]["by_category"]
    try:
        import data_sources as DS
        mix = Counter(q.category for s in DS.eval_sessions().values() for q in s.questions)
    except Exception:                                                         # noqa: BLE001
        mix = Counter({k: 1 for k in cl})
    num = sum(mix[c] * (float(cl[c]["accuracy"]) - float(dv[c]["accuracy"])) for c in cl if c in dv and mix[c])
    den = sum(mix[c] for c in cl if c in dv and mix[c]) or 1
    return dict(recall=max(num / den, 1e-3), dashcam=0.090)


class HybridArm:
    """Built on the committed b7 live2 wrapper; see the module docstring."""

    SWITCHES = ("c1", "c2", "c3", "c4", "c5", "c6")

    def __init__(self, name: str = "hybrid-base", c1=False, c2=False, c3=False, c4=False, c5=False, c6=False,
                 k_r: float = 1.0, m_d: float = 0.05) -> None:
        from arms_published import B7EdfFeasibilityArm
        self._b7 = B7EdfFeasibilityArm()
        self.name = name
        self.sw = dict(c1=bool(c1), c2=bool(c2), c3=bool(c3), c4=bool(c4), c5=bool(c5), c6=bool(c6))
        self.k_r, self.m_d = float(k_r), float(m_d)
        self.values = _quality_values() if any(self.sw.values()) else None
        self.cap, self._last_adj = 8, None
        self.stats = Counter()

    # ---- delegate every live2 hook to the committed b7 wrapper (the base) --------------------------------
    def __getattr__(self, k):
        return getattr(self.__dict__["_b7"], k)

    def __call__(self, obs: Observation) -> Action:
        # identical entry path to b7's (Policy.__call__ scrubs, validates, applies defaults), with our decide
        return self._b7.__class__.__call__(self, obs) if hasattr(self._b7.__class__, "__call__") else self.decide(obs)

    def live2_describe(self) -> Dict[str, Any]:
        d = dict(self._b7.live2_describe()) if hasattr(self._b7, "live2_describe") else {}
        d.update(hybrid=dict(self.sw, k_r=self.k_r, m_d=self.m_d), hybrid_name=self.name)
        return d

    # ---- the decision ------------------------------------------------------------------------------------
    def decide(self, obs: Observation) -> Action:
        if not any(self.sw.values()):
            return self._b7.decide(obs)                        # THE BASE: b7 exactly
        now = obs.now_s
        in_flight = sum(int(v) for v in (obs.cloud.running_by_class or {}).values())
        roster = (getattr(self._b7, "_live2_roster", None) or {}).get("sh_instant", {})
        epi_s = float(C.episodic_cloud_latency_s("32BI", 1, 25))
        items = []
        for s in obs.streams:                                  # dashcam instants
            inst = roster.get(s.stream_id)
            dl = float(inst["deadline_abs"]) if inst else now + DASH_DEADLINE_S
            slack = dl - now - epi_s
            recent = [t for t in s.delivered_times_s if t > now - 60.0]
            frac = len(recent) / max(60.0 / max(s.cadence_s, 1e-3), 1.0)
            risk = self.sw["c2"] and (frac < 0.25 + self.m_d)
            items.append(dict(kind="dash", id=s.stream_id, dl=dl, slack=slack, work=epi_s, risk=risk,
                              value=(self.values or {}).get("dashcam", 0.09)))
        rec_dec: Dict[str, RecallAction] = {}
        for q in sorted(obs.recall, key=lambda x: x.deadline_s):
            est = float(C.recall_ttft_s(max(q.readiness_tokens, 1), q.readiness))
            qs = q.slack_s(now)
            slack = qs - est
            risk = self.sw["c2"] and (qs < self.k_r or slack < 0)
            if est <= qs:
                d = RecallAction(q.query_id, "CLOUD")
            elif est <= qs + self._b7.defer_s:
                d = RecallAction(q.query_id, "DEFER", defer_s=self._b7.defer_s)
            else:
                d = RecallAction(q.query_id, "REJECT")
            if self.sw["c3"] and d.decision != "CLOUD":
                est_r = float(C.recall_ttft_s(RECENT_TOKENS, "COLD"))
                if est_r <= qs:
                    d = RecallAction(q.query_id, "CLOUD", representation="RECENT")
                    self.stats["c3_recent"] += 1
            rec_dec[q.query_id] = d
            if d.decision == "CLOUD":
                items.append(dict(kind="recall", id=q.query_id, dl=q.deadline_s, slack=slack, risk=risk,
                                  work=float(C.recall_gpu_s(max(q.readiness_tokens, 1), q.readiness)),
                                  value=(self.values or {}).get("recall", 0.1)))
        # order
        def idx(it):
            return it["value"] * (1.0 / max(it["slack"], 0.1)) / max(it["work"], 1e-3)
        if self.sw["c1"]:
            items.sort(key=lambda it: (not it["risk"], -idx(it), it["dl"], it["id"]))
        else:
            items.sort(key=lambda it: (not it["risk"], it["dl"], it["id"]))
        # cap (C5); without C5 the base has none, as b7
        if self.sw["c5"]:
            self._aimd(obs)
            budget = max(self.cap - in_flight, 0)
            chosen, reserved = [], 1 if self.sw["c2"] else 0
            for it in items:
                if len(chosen) >= budget:
                    break
                if reserved and it["kind"] != "recall" and len(chosen) >= budget - reserved \
                        and not any(x["kind"] == "recall" and x["risk"] for x in chosen):
                    if any(x["kind"] == "recall" and x["risk"] for x in items):
                        continue                           # keep the slot for at-risk recall work
                chosen.append(it)
            keep = {(it["kind"], it["id"]) for it in chosen}
        else:
            keep = {(it["kind"], it["id"]) for it in items}
        order = [it for it in items if (it["kind"], it["id"]) in keep]
        streams = [StreamAction(it["id"], "cloud") for it in order if it["kind"] == "dash"]
        streams += [StreamAction(s.stream_id, "local") for s in obs.streams if ("dash", s.stream_id) not in keep]
        recall = []
        for it in order:
            if it["kind"] == "recall":
                recall.append(rec_dec[it["id"]])
        for qid, d in rec_dec.items():
            if d.decision == "CLOUD" and ("recall", qid) not in keep:
                recall.append(RecallAction(qid, "DEFER", defer_s=0.0))
            elif d.decision != "CLOUD":
                recall.append(d)
        self.stats["decisions"] += 1
        return Action(streams=streams, recall=recall, order="EDF", notes={"hybrid": self.name})

    def _aimd(self, obs: Observation) -> None:
        lat = (obs.cloud.latency_estimate_s or {}).get("episodic")
        now = obs.now_s
        if lat is not None and lat > 0.8 * DASH_DEADLINE_S:
            if self._last_adj is None or now - self._last_adj >= 1.0:
                self.cap = max(4, self.cap // 2)
                self._last_adj = now
                self.stats["c5_decrease"] += 1
        elif self._last_adj is None or now - self._last_adj >= 5.0:
            if self.cap < 8:
                self.cap += 1
                self.stats["c5_increase"] += 1
            self._last_adj = now


CONFIGS: Dict[str, Dict[str, Any]] = {
    "hybrid-base": {},
    "hybrid-c1": dict(c1=True),
    "hybrid-c1c2k1": dict(c1=True, c2=True, k_r=1.0),
    "hybrid-c1c2k2": dict(c1=True, c2=True, k_r=2.0),
    "hybrid-c1c2k1c3": dict(c1=True, c2=True, c3=True, k_r=1.0),
    "hybrid-c1c2k2c3": dict(c1=True, c2=True, c3=True, k_r=2.0),
    "hybrid-c5": dict(c5=True),
    "hybrid-c1c5": dict(c1=True, c5=True),
    "hybrid-c1c2k1c5": dict(c1=True, c2=True, c5=True, k_r=1.0),
    "hybrid-c1c2k2c5": dict(c1=True, c2=True, c5=True, k_r=2.0),
    "hybrid-all-k1": dict(c1=True, c2=True, c3=True, c5=True, k_r=1.0),
    "hybrid-all-k2": dict(c1=True, c2=True, c3=True, c5=True, k_r=2.0),
}


def register() -> None:
    import arms as A
    for name, kw in CONFIGS.items():
        A.ARMS[name] = (lambda n=name, k=kw: HybridArm(name=n, **k))
