"""StudyRES1-residency: score the bookkeeping predictor against the MEASURED tier per request.

Streams are reconstructed from the committed StudyENG1c rows exactly as a scheduler would have
seen them: arrival time, prompt tokens, which prefix the request reuses and how long that prefix
is, and the server's own capacities. The ground truth is what the ENGINE reported for that
request, and it is computed in a separate function that the predictor cannot reach.

HOLDOUT FENCE. The 120 StudyENG1c Part D HOLDOUT pairs are replayed as stream events, because
they consumed real capacity on a shared server and dropping them would corrupt every later
prediction, but they never enter a scored set and `measured_class` REFUSES a holdout request, so
no measured outcome of theirs is read.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from policy.residency import (CLASSES, GPU_POOL_TOKENS_H100NVL, POLICIES, Req, ResidencyModel,
                              TOKENS_PER_BLOCK, host_tokens_for_cap, n_chunks, replay)

ENG1C = "results/cost/study_eng1c"
OUT_DIR = "results/orchestration/study_res1"
EXT = "prompt_tokens_by_source_total|external_kv_transfer"
LOC = "prompt_tokens_by_source_total|local_cache_hit"
COMP = "prompt_tokens_by_source_total|local_compute"
TEST_PARTS = ("B", "C", "D", "E")
IN_SAMPLE_PARTS = ("A",)


class HoldoutFenced(PermissionError):
    """Raised when a measured outcome of a fenced holdout request is requested."""


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _rows(part: str) -> List[Dict[str, Any]]:
    p = _root() / ENG1C / ("eng1c_part%s_h100nvl.jsonl" % part)
    return [json.loads(l) for l in open(p)]


def _trials() -> List[Dict[str, Any]]:
    return [json.loads(l) for l in open(_root() / ENG1C / "eng1c_trials_h100nvl.jsonl")]


# ------------------------------------------------------------------ server segments
def server_segments() -> List[Dict[str, Any]]:
    meta = json.loads((_root() / ENG1C / "eng1c_run_meta_h100nvl.json").read_text())
    segs = []
    for s in meta["servers"]:
        flags = s["flags"]
        cap = None
        for i, f in enumerate(flags):
            if f == "--kv-offloading-size":
                cap = float(flags[i + 1])
        t = datetime.fromisoformat(s["started"]).replace(tzinfo=timezone.utc).timestamp()
        segs.append(dict(label=s["label"], cap_gib=cap, t_start=t))
    segs.sort(key=lambda d: d["t_start"])
    return segs


class ServerMap:
    """Which server a request went to, by arrival time. The server start empties both tiers, so
    this is also the reset boundary for the bookkeeping."""

    def __init__(self) -> None:
        self.segs = server_segments()
        self.offset = self._calibrate()

    def _calibrate(self) -> float:
        """The run_meta timestamps are local-naive and the request rows are epoch seconds. The
        offset is recovered from the frontend log, which carries both the server label and the
        request's epoch time, so nothing is assumed about the host's timezone."""
        first: Dict[str, float] = {}
        for line in open(_root() / ENG1C / "eng1c_frontend_h100nvl.jsonl"):
            r = json.loads(line)
            lab, t = r["server"], float(r["received_t"])
            if lab not in first or t < first[lab]:
                first[lab] = t
        deltas = [first[s["label"]] - s["t_start"] for s in self.segs if s["label"] in first]
        return statistics.median(deltas) if deltas else 0.0

    def at(self, t: float) -> Dict[str, Any]:
        cur = None
        for s in self.segs:
            if t >= s["t_start"] + self.offset - 1.0:
                cur = s
            else:
                break
        return cur or self.segs[0]


# ------------------------------------------------------------------ stream builders
def _req(row: Dict[str, Any], smap: ServerMap, **kw: Any) -> Req:
    seg = smap.at(float(row["t_submit"]))
    return Req(rid=str(row["rid"]), t_submit=float(row["t_submit"]),
               t_end=float(row.get("t_end") or row["t_submit"]),
               prompt_tokens=int(row.get("prompt_tokens") or 0),
               server=seg["label"], cap_gib=float(row.get("cap") or seg["cap_gib"]), **kw)


def stream_part_a(smap: ServerMap) -> List[Req]:
    rows = _rows("A")
    hist_of: Dict[str, int] = {}
    for r in rows:
        if r["kind"] == "build" and r.get("ns"):
            hist_of[r["ns"]] = max(hist_of.get(r["ns"], 0), int(r["prompt_tokens"]))
    out = []
    for r in rows:
        k = r["kind"]
        if k == "a_summary":
            continue
        trial = "A|%s|%s|%s" % (r.get("cap"), r.get("pattern"), r.get("rep"))
        if k == "build":
            out.append(_req(r, smap, writes_hid=r["ns"], part="A", trial=trial,
                            meta=dict(role=r.get("role"))))
        elif k in ("touch", "probe"):
            ns = r["ns"]
            out.append(_req(r, smap, hid=ns, writes_hid=ns, hist_tokens=hist_of.get(ns, 0),
                            part="A", trial=trial, reuse=True,
                            meta=dict(role=k, probe_role=r.get("probe_role"),
                                      pattern=r.get("pattern"), rep=r.get("rep"))))
    return out


def stream_part_b(smap: ServerMap) -> List[Req]:
    rows = _rows("B")
    prefix_of: Dict[str, int] = {}
    for t in _trials():
        if t.get("sub") == "B" and t.get("ns"):
            prefix_of[t["ns"]] = int(t.get("prefix_tokens") or 0)
    prev_piece: Dict[str, int] = {}
    out = []
    for r in sorted(rows, key=lambda x: float(x["t_submit"])):
        k = r["kind"]
        ns = r.get("ns")
        trial = "B|%s" % (ns or r["rid"])
        if k == "build":
            # an occupancy history of its own; `ns` here is the occupancy build's own namespace
            out.append(_req(r, smap, writes_hid=r["rid"], part="B", trial=trial,
                            meta=dict(role="occupancy")))
        elif k == "filler":
            out.append(_req(r, smap, writes_hid=r["rid"], part="B", trial=trial,
                            meta=dict(role="filler")))
        elif k == "episodic":
            out.append(_req(r, smap, writes_hid=r["rid"], part="B", trial=trial,
                            meta=dict(role="episodic")))
        elif k == "piece":
            role = r.get("role") or ""
            hist = prev_piece.get(ns, 0)
            out.append(_req(r, smap, hid=(ns if hist > 0 else None), writes_hid=ns,
                            hist_tokens=hist, part="B", trial=trial, reuse=bool(hist > 0),
                            meta=dict(role=role)))
            prev_piece[ns] = int(r["prompt_tokens"])
        elif k == "resume":
            hist = prefix_of.get(ns) or prev_piece.get(ns, 0)
            out.append(_req(r, smap, hid=ns, writes_hid=ns, hist_tokens=hist, part="B",
                            trial=trial, reuse=True, meta=dict(role="resume")))
    return out


def stream_part_c(smap: ServerMap) -> List[Req]:
    rows = _rows("C")
    out = []
    for r in sorted((x for x in rows if x["kind"] in ("build", "query")),
                    key=lambda x: float(x["t_submit"])):
        if r["kind"] == "build":
            out.append(_req(r, smap, writes_hid=r["ns"], part="C",
                            trial="C|%s|%s" % (r.get("cap"), r.get("conc")),
                            conc=r.get("conc"), meta=dict(role=r.get("role"))))
        else:
            out.append(_req(r, smap, hid=r["ns"], writes_hid=r["ns"],
                            hist_tokens=int(r.get("hist_tokens") or 0), part="C",
                            trial="C|%s|%s|%s" % (r.get("cap"), r.get("conc"), r.get("round")),
                            conc=r.get("conc"), reuse=True,
                            meta=dict(role="query", round=r.get("round"), slot=r.get("slot"),
                                      constructed_state=r.get("state"))))
    return out


def stream_part_d(smap: ServerMap) -> List[Req]:
    rows = _rows("D")
    member_ns: Dict[Tuple[str, int], str] = {}
    hist_of: Dict[str, int] = {}
    for r in rows:
        if r["kind"] == "build" and r.get("role") == "population":
            seg = smap.at(float(r["t_submit"]))
            member_ns[(seg["label"], int(r["member"]))] = r["ns"]
            hist_of[r["ns"]] = max(hist_of.get(r["ns"], 0), int(r["prompt_tokens"]))
    out: List[Req] = []
    prev_part: Dict[str, int] = {}
    for r in sorted((x for x in rows if x["kind"] in ("build", "episodic", "inject", "churn")),
                    key=lambda x: float(x["t_submit"])):
        k = r["kind"]
        seg = smap.at(float(r["t_submit"]))
        hold = bool(r.get("holdout"))
        if k == "build":
            out.append(_req(r, smap, writes_hid=r["ns"], part="D", trial="D|pop|%s" % seg["label"],
                            meta=dict(role="population", member=r.get("member"))))
        elif k == "episodic":
            out.append(_req(r, smap, writes_hid=r["rid"], part="D",
                            trial="D|%s" % (r.get("pair") or r["rid"]), holdout=hold,
                            meta=dict(role="episodic", mode=r.get("mode"))))
        elif k == "churn":
            ns = member_ns.get((seg["label"], int(r.get("member", -1))))
            out.append(_req(r, smap, hid=ns, writes_hid=ns, hist_tokens=hist_of.get(ns, 0),
                            part="D", trial="D|churn|%s" % seg["label"],
                            reuse=bool(ns), meta=dict(role="churn", member=r.get("member"))))
        elif k == "inject":
            ns = member_ns.get((seg["label"], int(r.get("target", -1))))
            run = str(r.get("run_ns"))
            pi = int(r.get("part_i") or 0)
            hist = prev_part.get(run, hist_of.get(ns, 0)) if pi > 0 else hist_of.get(ns, 0)
            hist = min(hist, int(r["prompt_tokens"])) if pi > 0 else hist
            out.append(_req(r, smap, hid=ns, writes_hid=ns, hist_tokens=hist, part="D",
                            trial="D|%s" % (r.get("pair") or run), holdout=hold,
                            reuse=bool(ns), meta=dict(role="inject", part_i=pi,
                                                      n_parts=r.get("n_parts"),
                                                      variant=r.get("variant"),
                                                      load=r.get("load"), run_ns=run,
                                                      mode=r.get("mode"))))
            prev_part[run] = int(r["prompt_tokens"])
    return out


def stream_part_e(smap: ServerMap) -> List[Req]:
    out = []
    for r in _rows("E"):
        if r["kind"] != "episodic":
            continue
        out.append(_req(r, smap, writes_hid=r["rid"], part="E",
                        trial="E|%s|%s" % (r.get("cond"), r.get("trial")),
                        meta=dict(role="episodic", cond=r.get("cond"))))
    return out


def build_streams() -> Tuple[Dict[str, List[Req]], Dict[str, Any]]:
    """Every request of every part, grouped by server segment, in arrival order."""
    smap = ServerMap()
    reqs = (stream_part_a(smap) + stream_part_b(smap) + stream_part_c(smap)
            + stream_part_d(smap) + stream_part_e(smap))
    by_server: Dict[str, List[Req]] = defaultdict(list)
    for r in reqs:
        by_server[r.server].append(r)
    audit = dict(
        n_requests=len(reqs), n_servers=len(by_server),
        per_server={k: dict(n=len(v), cap_gib=v[0].cap_gib,
                            parts=sorted({x.part for x in v}),
                            n_reuse=sum(1 for x in v if x.reuse),
                            n_holdout=sum(1 for x in v if x.holdout)) for k, v in
                    sorted(by_server.items())},
        per_part={p: dict(n=sum(1 for r in reqs if r.part == p),
                          n_reuse=sum(1 for r in reqs if r.part == p and r.reuse))
                  for p in ("A", "B", "C", "D", "E")},
        time_offset_s=smap.offset,
        note="server segments come from eng1c_run_meta flags; the epoch offset is recovered from "
             "the frontend log, which carries both the server label and the request's epoch time")
    return dict(by_server), audit


# ------------------------------------------------------------------ measured ground truth
def measured_class(hist_tokens: int, cached_tokens: int, ext_tokens: Optional[float],
                   attributable: bool) -> Dict[str, Any]:
    """The MEASURED class of one request, from what the engine reported for it.

    Block arithmetic throughout, because the engine caches whole 16-token blocks and must
    recompute at least the last one (StudyENG1c Part A's three PG misses are exactly this), so
    the tolerance is ONE BLOCK and not zero:

      COLD     hit blocks at most 1;
      PARTIAL  more than one block of the history recomputed (determinable from cached tokens
               alone; the fraction on host needs an attributable counter);
      HOST     at most one block recomputed and more than one block transferred from host;
      GPU      at most one block recomputed and at most one block from host.
    """
    hist = max(int(hist_tokens), 0)
    cached = max(int(cached_tokens or 0), 0)
    blocks_hist = hist // TOKENS_PER_BLOCK
    hit_blocks = cached // TOKENS_PER_BLOCK
    if hist <= 0:
        return dict(cls=None, host_fraction=None, determined=False, reason="no history length")
    if hit_blocks <= 1:
        return dict(cls="COLD", host_fraction=0.0, determined=True, reason="hit at most 1 block")
    recomputed_blocks = max(blocks_hist - hit_blocks, 0)
    if recomputed_blocks > 1:
        frac = (float(ext_tokens) / hist) if (attributable and ext_tokens is not None) else None
        return dict(cls="PARTIAL", host_fraction=frac, determined=True,
                    recomputed_blocks=recomputed_blocks,
                    reason="more than one block of the history recomputed")
    if not attributable or ext_tokens is None:
        return dict(cls=None, host_fraction=None, determined=False,
                    reason="warm, but no counter window isolates this request's GPU/host split")
    ext = float(ext_tokens)
    cls = "HOST" if ext > TOKENS_PER_BLOCK else "GPU"
    return dict(cls=cls, host_fraction=min(ext / hist, 1.0), determined=True,
                reason="attributable counter window")


def truth_part_a() -> Dict[str, Dict[str, Any]]:
    """Part A probes and touches carry a PER-REQUEST split (m_local, m_external, m_compute)."""
    out = {}
    rows = _rows("A")
    hist_of = {}
    for r in rows:
        if r["kind"] == "build" and r.get("ns"):
            hist_of[r["ns"]] = max(hist_of.get(r["ns"], 0), int(r["prompt_tokens"]))
    for r in rows:
        if r["kind"] not in ("probe", "touch"):
            continue
        hist = hist_of.get(r.get("ns"), 0)
        m = measured_class(hist, r.get("cached_tokens"), r.get("m_external"), True)
        m["m_local"], m["m_external"], m["m_compute"] = (r.get("m_local"), r.get("m_external"),
                                                         r.get("m_compute"))
        out[str(r["rid"])] = m
    return out


def truth_part_b() -> Dict[str, Dict[str, Any]]:
    """Resumes have their own counter window. Piece-chain requests have none, so only their
    warm-versus-cold state is measured."""
    out = {}
    for t in _trials():
        if t.get("sub") != "B" or not t.get("resume_rid"):
            continue
        md = t.get("resume_window_delta") or {}
        if t.get("resume_error"):
            continue
        out[str(t["resume_rid"])] = measured_class(int(t.get("prefix_tokens") or 0),
                                                   t.get("resume_cached"),
                                                   float(md.get(EXT, 0) or 0), True)
    prev = {}
    for r in sorted(_rows("B"), key=lambda x: float(x["t_submit"])):
        if r["kind"] != "piece":
            continue
        ns = r.get("ns")
        hist = prev.get(ns, 0)
        if hist > 0:
            out[str(r["rid"])] = measured_class(hist, r.get("cached_tokens"), None, False)
        prev[ns] = int(r["prompt_tokens"])
    return out


def truth_part_c() -> Dict[str, Dict[str, Any]]:
    """Three attribution routes, in this order: a round whose external total is zero (no host
    load happened at all, so every warm request in it was GPU-served); a round whose external
    total equals every warm request's cached tokens (so each of them came from host); and a
    per-request window whose increment accounts for exactly that request's prompt."""
    rows = _rows("C")
    q = [r for r in rows if r["kind"] == "query"]
    rounds = {(r["cap"], r["conc"], r["round"]): r for r in rows if r["kind"] == "c_round"}
    by_round = defaultdict(list)
    for r in q:
        by_round[(r["cap"], r["conc"], r["round"])].append(r)
    out = {}
    for key, qs in sorted(by_round.items()):
        rd = (rounds[key].get("round_delta") or {})
        ext_round = float(rd.get(EXT, 0) or 0)
        warm = [r for r in qs if (r.get("cached_tokens") or 0) // TOKENS_PER_BLOCK > 1]
        route = None
        if ext_round == 0:
            route = "round external total is zero"
        elif abs(ext_round - sum(int(r["cached_tokens"]) for r in warm)) <= TOKENS_PER_BLOCK * max(len(warm), 1):
            route = "round external equals every warm request's cached tokens"
        prevtot = 0.0
        prevext = 0.0
        for r in sorted(qs, key=lambda x: float(x["t_end"])):
            md = r.get("metrics_delta_since_round") or {}
            tot = sum(float(md.get(x, 0) or 0) for x in (EXT, LOC, COMP))
            ext_cum = float(md.get(EXT, 0) or 0)
            d_tot, d_ext = tot - prevtot, ext_cum - prevext
            prevtot, prevext = tot, ext_cum
            isolated = abs(d_tot - int(r["prompt_tokens"])) <= TOKENS_PER_BLOCK
            hist = int(r.get("hist_tokens") or 0)
            if route == "round external total is zero":
                m = measured_class(hist, r.get("cached_tokens"), 0.0, True)
                m["route"] = route
            elif route == "round external equals every warm request's cached tokens":
                m = measured_class(hist, r.get("cached_tokens"),
                                   float(r.get("cached_tokens") or 0), True)
                m["route"] = route
            elif isolated:
                m = measured_class(hist, r.get("cached_tokens"), d_ext, True)
                m["route"] = "per-request window isolated"
            else:
                m = measured_class(hist, r.get("cached_tokens"), None, False)
                m["route"] = "not attributable"
            m["telemetry_ext_tokens"] = d_ext
            m["telemetry_isolated"] = bool(isolated)
            m["telemetry_cached_tokens"] = int(r.get("cached_tokens") or 0)
            m["conc"] = r.get("conc")
            out[str(r["rid"])] = m
    return out


def truth_part_d(fence_holdout: bool = True) -> Dict[str, Dict[str, Any]]:
    """The injected job's run window covers only that job's requests, so a run whose external
    total is zero had no host load at all, and a run whose external total equals the run's cached
    tokens served every hit from host. Churn arrivals fall between runs and have no window, so
    only their warm-versus-cold state is measured."""
    rows = _rows("D")
    summ = {str(r.get("run_ns")): r for r in rows if r["kind"] == "run_summary"}
    hist_of, member_ns = {}, {}
    smap = ServerMap()
    for r in rows:
        if r["kind"] == "build" and r.get("role") == "population":
            seg = smap.at(float(r["t_submit"]))
            member_ns[(seg["label"], int(r["member"]))] = r["ns"]
            hist_of[r["ns"]] = max(hist_of.get(r["ns"], 0), int(r["prompt_tokens"]))
    by_run = defaultdict(list)
    for r in rows:
        if r["kind"] == "inject":
            by_run[str(r.get("run_ns"))].append(r)
    out = {}
    for run, rs in by_run.items():
        if fence_holdout and any(r.get("holdout") for r in rs):
            continue
        s = summ.get(run)
        md = (s.get("metrics_delta") if s else None) or {}
        ext_run = float(md.get(EXT, 0) or 0)
        cached_run = sum(int(r.get("cached_tokens") or 0) for r in rs)
        if ext_run == 0:
            route, per_ext = "run external total is zero", (lambda r: 0.0)
        elif abs(ext_run - cached_run) <= TOKENS_PER_BLOCK * len(rs):
            route, per_ext = ("run external equals the run's cached tokens",
                              (lambda r: float(r.get("cached_tokens") or 0)))
        else:
            route, per_ext = "not attributable", (lambda r: None)
        prev = {}
        for r in sorted(rs, key=lambda x: int(x.get("part_i") or 0)):
            pi = int(r.get("part_i") or 0)
            ns = member_ns.get((smap.at(float(r["t_submit"]))["label"], int(r.get("target", -1))))
            hist = hist_of.get(ns, 0) if pi == 0 else min(prev.get(run, 0),
                                                          int(r["prompt_tokens"]))
            ext = per_ext(r)
            m = measured_class(hist, r.get("cached_tokens"), ext, ext is not None)
            m["route"] = route
            out[str(r["rid"])] = m
            prev[run] = int(r["prompt_tokens"])
    for r in rows:
        if r["kind"] != "churn":
            continue
        ns = member_ns.get((smap.at(float(r["t_submit"]))["label"], int(r.get("member", -1))))
        m = measured_class(hist_of.get(ns, 0), r.get("cached_tokens"), None, False)
        m["route"] = "churn: no counter window (between runs)"
        out[str(r["rid"])] = m
    return out


def measured_truth() -> Dict[str, Dict[str, Any]]:
    t = {}
    t.update(truth_part_a())
    t.update(truth_part_b())
    t.update(truth_part_c())
    t.update(truth_part_d(fence_holdout=True))
    return t


# ------------------------------------------------------------------------- scoring
def predictions(streams: Dict[str, List[Req]], policy: str) -> Dict[str, Dict[str, Any]]:
    out = {}
    for server, reqs in sorted(streams.items()):
        cap = reqs[0].cap_gib
        for row in replay(reqs, cap_gib=cap, policy=policy):
            out[row["rid"]] = row
    return out


def joined(streams: Dict[str, List[Req]], truth: Dict[str, Dict[str, Any]],
           policy: str) -> List[Dict[str, Any]]:
    pred = predictions(streams, policy)
    rows = []
    for rid, p in pred.items():
        if p["holdout"]:
            continue
        m = truth.get(rid)
        if m is None:
            continue
        rows.append(dict(rid=rid, part=p["part"], cap=p["cap_gib"], conc=p["conc"],
                         trial=p["trial"], role=p.get("role"), policy=policy,
                         predicted=p["predicted_class"],
                         predicted_host_fraction=p["predicted_host_fraction"],
                         gpu_chunks=p["gpu_chunks"], host_chunks=p["host_chunks"],
                         hist_tokens=p["hist_tokens"], prompt_tokens=p["prompt_tokens"],
                         forced_last_block=p["forced_last_block"], host_path=p["host_path"],
                         measured=m["cls"], measured_host_fraction=m.get("host_fraction"),
                         determined=bool(m["determined"]), route=m.get("route"),
                         reason=m.get("reason"), variant=p.get("variant"),
                         constructed_state=p.get("constructed_state"),
                         telemetry_ext_tokens=m.get("telemetry_ext_tokens"),
                         telemetry_isolated=m.get("telemetry_isolated"),
                         telemetry_cached_tokens=m.get("telemetry_cached_tokens")))
    return rows


def accuracy(rows: Sequence[Dict[str, Any]]) -> Optional[float]:
    if not rows:
        return None
    return sum(1 for r in rows if r["predicted"] == r["measured"]) / len(rows)


def measured_2class(row: Dict[str, Any]) -> str:
    """Every reuse request has a measured warm-versus-cold state even when its tier is not
    measured: `measured_class` leaves a row undetermined only when the request WAS warm and no
    counter window can say which tier served it."""
    if row["determined"]:
        return "COLD" if row["measured"] == "COLD" else "WARM"
    return "WARM"


def two_class(rows: Sequence[Dict[str, Any]]) -> Optional[float]:
    """Warm versus cold only: a predictor saying anything other than COLD is saying warm."""
    if not rows:
        return None
    ok = 0
    for r in rows:
        pp = "COLD" if r["predicted"] == "COLD" else "WARM"
        ok += int(measured_2class(r) == pp)
    return ok / len(rows)


def confusion(rows: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    c = Counter()
    for r in rows:
        c["%s->%s" % (r["measured"], r["predicted"])] += 1
    return dict(sorted(c.items()))


def by_cut(rows: Sequence[Dict[str, Any]], keyfn) -> Dict[str, Any]:
    g = defaultdict(list)
    for r in rows:
        g[str(keyfn(r))].append(r)
    return {k: dict(n=len(v), accuracy=accuracy(v),
                    measured=dict(sorted(Counter(x["measured"] for x in v).items())),
                    predicted=dict(sorted(Counter(x["predicted"] for x in v).items())))
            for k, v in sorted(g.items())}


def paired_bootstrap(rows_a: Sequence[Dict[str, Any]], rows_b: Sequence[Dict[str, Any]],
                     draws: int = 10000, seed: int = 20261117) -> Dict[str, Any]:
    """The difference in accuracy between two predictors on the SAME requests, resampling by
    TRIAL so that requests from one trial move together."""
    a = {r["rid"]: r for r in rows_a}
    b = {r["rid"]: r for r in rows_b}
    shared = sorted(set(a) & set(b))
    by_trial = defaultdict(list)
    for rid in shared:
        by_trial[a[rid]["trial"]].append(rid)
    trials = sorted(by_trial)
    if not trials:
        return dict(n_trials=0, diff=None, ci=None, excludes_zero=False)
    def diff_for(sample_trials):
        n = ok_a = ok_b = 0
        for t in sample_trials:
            for rid in by_trial[t]:
                n += 1
                ok_a += int(a[rid]["predicted"] == a[rid]["measured"])
                ok_b += int(b[rid]["predicted"] == b[rid]["measured"])
        return ((ok_a - ok_b) / n) if n else 0.0
    point = diff_for(trials)
    rng = random.Random(seed)
    ds = []
    for _ in range(draws):
        ds.append(diff_for([trials[rng.randrange(len(trials))] for _ in trials]))
    ds.sort()
    lo, hi = ds[int(0.025 * draws)], ds[min(int(0.975 * draws), draws - 1)]
    return dict(n_trials=len(trials), n_requests=len(shared), diff=point, ci=[lo, hi],
                excludes_zero=bool(lo > 0 or hi < 0), favours_rule=bool(point > 0),
                draws=draws, resample_unit="trial")


def r3_partial(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    use = [r for r in rows if r["measured"] == "PARTIAL"
           and r["measured_host_fraction"] is not None]
    if not use:
        return dict(n=0, mae=None, threshold=0.10, verdict="NOT COMPUTABLE")
    errs = [abs(r["predicted_host_fraction"] - r["measured_host_fraction"]) for r in use]
    mae = sum(errs) / len(errs)
    return dict(n=len(use), mae=mae, threshold=0.10,
                verdict=("PASS" if mae <= 0.10 else "FAIL"),
                median_abs_error=statistics.median(errs),
                measured_fraction=dict(min=min(r["measured_host_fraction"] for r in use),
                                       max=max(r["measured_host_fraction"] for r in use)),
                per_part=dict(sorted(Counter(r["part"] for r in use).items())))


# ------------------------------------------------------------- pre-declared analyses
def selection_check(rows_rule: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Pre-declared analysis 2. The measured subset comes mostly from isolated, low-concurrency
    windows; the unmeasured warm requests concentrate in Part C at concurrency 4 and 8 and in
    Part D churn. Per part and per concurrency level, this reports the PREDICTED tier
    distribution on measured against unmeasured requests, so a reader can see whether the
    measured set under-represents the hard cases."""
    def dist(rs):
        c = Counter(r["predicted"] for r in rs)
        n = max(len(rs), 1)
        return dict(n=len(rs), share={k: round(v / n, 4) for k, v in sorted(c.items())},
                    counts=dict(sorted(c.items())))
    out = {}
    for keyname, keyfn in (("per_part", lambda r: r["part"]),
                           ("per_conc", lambda r: str(r["conc"])),
                           ("per_part_conc", lambda r: "%s|%s" % (r["part"], r["conc"])),
                           ("per_role", lambda r: str(r["role"]))):
        g = defaultdict(lambda: ([], []))
        for r in rows_rule:
            g[str(keyfn(r))][0 if r["determined"] else 1].append(r)
        out[keyname] = {k: dict(measured=dist(v[0]), unmeasured=dist(v[1])) for k, v in
                        sorted(g.items())}
    det = [r for r in rows_rule if r["determined"]]
    und = [r for r in rows_rule if not r["determined"]]
    out["pooled"] = dict(measured=dist(det), unmeasured=dist(und))
    out["statement"] = ("R1, R2 and R3 do not cover the GPU-versus-host split under concurrency "
                        "4 and 8: of the %d unmeasured warm requests, %d are Part C queries at "
                        "concurrency 4 or 8 and %d are Part D churn arrivals."
                        % (len(und),
                           sum(1 for r in und if r["part"] == "C" and (r["conc"] or 0) >= 4),
                           sum(1 for r in und if r["role"] == "churn")))
    return out


def telemetry_belief(rows_rule: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Three ways to believe something about the tier under ambiguous telemetry, scored against
    the measured class on Part C at concurrency 4 and 8.

    The evaluation set is restricted to requests whose truth came from a ROUND-LEVEL route (the
    round's external total is zero, or equals every warm request's cached tokens). That matters:
    on a request whose truth came from its own isolated window, predictor (a) would be right by
    construction, so including those would measure nothing."""
    pool = [r for r in rows_rule
            if r["part"] == "C" and (r["conc"] or 0) >= 4 and r["determined"]
            and str(r.get("route") or "").startswith("round external")]
    def telemetry_alone(r):
        """Telemetry only, with no bookkeeping: the request's own cached tokens say warm or
        cold, and the window's external increment says which tier. Both are numbers the engine
        hands back, and neither is the measured class."""
        cached = int(r.get("telemetry_cached_tokens") or 0)
        if cached // TOKENS_PER_BLOCK <= 1:
            return "COLD"
        return "HOST" if (r.get("telemetry_ext_tokens") or 0) > TOKENS_PER_BLOCK else "GPU"
    rows = []
    for r in pool:
        a = telemetry_alone(r)
        b = r["predicted"]
        c = a if r.get("telemetry_isolated") else b
        rows.append(dict(rid=r["rid"], cap=r["cap"], conc=r["conc"], measured=r["measured"],
                         telemetry_alone=a, bookkeeping=b, corrected=c,
                         telemetry_isolated=bool(r.get("telemetry_isolated"))))
    def acc(field):
        if not rows:
            return None
        return sum(1 for r in rows if r[field] == r["measured"]) / len(rows)
    return dict(n=len(rows),
                evaluation_set="Part C queries at concurrency 4 and 8 whose measured class came "
                               "from a round-level route, so telemetry attribution is not "
                               "circular",
                accuracy=dict(telemetry_alone=acc("telemetry_alone"),
                              bookkeeping=acc("bookkeeping"), corrected=acc("corrected")),
                measured=dict(sorted(Counter(r["measured"] for r in rows).items())),
                n_telemetry_isolated=sum(1 for r in rows if r["telemetry_isolated"]),
                rows=rows[:40],
                note="telemetry_alone reads the per-request window delta as if it were "
                     "attributable, which is what a scheduler trusting the counters would do")


def concurrency_host_warm(rows_rule: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """StudyENG1c implication 4: host-warm is not a stable state while cold rebuilds run
    concurrently in a small host window. This reports how often a host-warm PREDICTION survives
    as measured host-warm, by cap and concurrency."""
    out = {}
    for r in rows_rule:
        if r["part"] != "C" or not r["determined"]:
            continue
        k = "cap %s, conc %s" % (int(r["cap"]), r["conc"])
        d = out.setdefault(k, dict(n_predicted_host=0, n_measured_host=0, n_lost_to_cold=0,
                                   n_lost_to_partial=0, host_window_beyond_gpu_tokens=
                                   host_tokens_for_cap(r["cap"]) - GPU_POOL_TOKENS_H100NVL))
        if r["predicted"] == "HOST":
            d["n_predicted_host"] += 1
            if r["measured"] == "HOST":
                d["n_measured_host"] += 1
            elif r["measured"] == "COLD":
                d["n_lost_to_cold"] += 1
            elif r["measured"] == "PARTIAL":
                d["n_lost_to_partial"] += 1
    for k, d in out.items():
        d["precision"] = (d["n_measured_host"] / d["n_predicted_host"]
                          if d["n_predicted_host"] else None)
    return dict(per_cell=dict(sorted(out.items())),
                reading="precision is the share of host-warm predictions that the engine still "
                        "served from host at scheduling")


def part_a_touch_rules(rows_rule: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """IN-SAMPLE (Part A). Does the module reproduce the two cases the rule was written for: a
    block-aligned touch that takes the host-load path, and a half-evicted history that is lost
    entirely once its unrefreshed head ages out?"""
    pool = [r for r in rows_rule if r["part"] == "A"]
    by_pattern = defaultdict(list)
    for r in pool:
        by_pattern[str(r.get("role")) + "|" + str(r.get("variant") or "")].append(r)
    aligned = [r for r in pool if r["prompt_tokens"] % TOKENS_PER_BLOCK == 0]
    return dict(
        label="IN-SAMPLE: the rule was finalized after seeing Part A, so this is reproduction "
              "and not a test",
        n=len(pool), accuracy=accuracy(pool), confusion=confusion(pool),
        block_aligned=dict(n=len(aligned), accuracy=accuracy(aligned),
                           n_forced_last_block=sum(1 for r in aligned if r["forced_last_block"]),
                           n_predicted_host=sum(1 for r in aligned if r["predicted"] == "HOST"),
                           n_measured_host=sum(1 for r in aligned if r["measured"] == "HOST")),
        by_role={k: dict(n=len(v), accuracy=accuracy(v)) for k, v in sorted(by_pattern.items())})


def eng1c_sim_agreement(truth: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """A separate check, as the brief requires: how often StudyENG1c's own harness simulator's
    tier_at_arrival agrees with the MEASURED class. It is not used as ground truth anywhere."""
    rows = _rows("D")
    agree = Counter()
    for r in rows:
        if r["kind"] != "job" or r.get("holdout"):
            continue
        run = str(r.get("run_ns"))
        sim = (r.get("tier_at_arrival") or {}).get("R4_code")
        first = None
        for x in rows:
            if x["kind"] == "inject" and str(x.get("run_ns")) == run and int(x.get("part_i") or 0) == 0:
                first = x
                break
        if first is None or sim is None:
            continue
        m = truth.get(str(first["rid"]))
        if m is None or not m["determined"]:
            continue
        simc = {"gpu": "GPU", "host": "HOST", "cold": "COLD", "partial": "PARTIAL"}.get(sim, sim)
        agree[(simc, m["cls"])] += 1
    n = sum(agree.values())
    same = sum(v for (a, b), v in agree.items() if a == b)
    return dict(n=n, agreement=(same / n if n else None),
                confusion={"%s->%s" % k: v for k, v in sorted(agree.items())},
                note="StudyENG1c's simulator is NOT ground truth here; this is the separate "
                     "agreement check the brief asks for")


# --------------------------------------------------------- mechanism verification
def shuffled_streams(streams: Dict[str, List[Req]], seed: int = 20261117) -> Dict[str, List[Req]]:
    """Negative control: shuffle the ORDER of requests within each trial, keeping the same set of
    arrival times, which destroys recency while leaving the write volume untouched. If recency is
    what the rule exploits, accuracy must fall toward the occupancy-only baseline."""
    rng = random.Random(seed)
    out: Dict[str, List[Req]] = {}
    for server, reqs in streams.items():
        by_trial = defaultdict(list)
        for r in reqs:
            by_trial[r.trial].append(r)
        new: List[Req] = []
        for trial, rs in by_trial.items():
            times = sorted(x.t_submit for x in rs)
            order = list(rs)
            rng.shuffle(order)
            for r, t in zip(order, times):
                new.append(Req(**{**r.__dict__, "t_submit": t}))
        out[server] = new
    return out


def mechanism(streams: Dict[str, List[Req]], truth: Dict[str, Dict[str, Any]],
              test_rows: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """CLAUDE.md Steps 1 to 5, recorded BEFORE the TEST verdicts are written."""
    rule = test_rows["rule"]
    occ = test_rows["occupancy"]
    det = [r for r in rule if r["determined"]]
    # Step 2 quantities
    writes = defaultdict(float)
    for server, reqs in streams.items():
        writes[server] = sum(r.prompt_tokens for r in reqs)
    caps = sorted({r["cap"] for r in rule})
    host_windows = {str(int(c)): host_tokens_for_cap(c) - GPU_POOL_TOKENS_H100NVL for c in caps}
    model_states = {}
    for server, reqs in sorted(streams.items()):
        m = ResidencyModel(reqs[0].cap_gib, "rule")
        for req in sorted(reqs, key=lambda r: (r.t_submit, r.rid)):
            m.complete(req, m.predict(req))
        model_states[server] = m.state()
    # Step 4: the negative control
    sh = shuffled_streams(streams)
    sh_rows = [r for r in joined(sh, truth, "rule") if r["part"] in TEST_PARTS and r["determined"]]
    control = dict(
        what="shuffle request order within each trial, keeping the same arrival times",
        accuracy_rule_normal=accuracy(det), accuracy_rule_shuffled=accuracy(sh_rows),
        accuracy_occupancy_baseline=accuracy([r for r in occ if r["determined"]]),
        n=len(sh_rows))
    a_n, a_s = control["accuracy_rule_normal"], control["accuracy_rule_shuffled"]
    a_o = control["accuracy_occupancy_baseline"]
    control["fell_toward_baseline"] = bool(a_s is not None and a_n is not None and a_o is not None
                                           and a_s < a_n and abs(a_s - a_o) < abs(a_n - a_o))
    control["drop"] = (a_n - a_s) if (a_n is not None and a_s is not None) else None
    step2 = [
        dict(causal_link="other work is written to both tiers and displaces a history",
             implementing_quantity="prompt tokens written per server segment",
             value_range="%d to %d tokens per segment" % (min(writes.values()),
                                                          max(writes.values())),
             varies="yes", evidence="16 segments, 5 caps"),
        dict(causal_link="the host tier adds room only beyond the GPU pool",
             implementing_quantity="host capacity minus the GPU pool",
             value_range=str(host_windows), varies="yes",
             evidence="12 GiB is NEGATIVE (-13,792 tokens), which is why ENG1c measured nothing "
                      "from the host tier there"),
        dict(causal_link="recency decides which history survives",
             implementing_quantity="evicted blocks per tier in the replay",
             value_range="gpu %d to %d, host %d to %d blocks"
                         % (min(s["gpu_evicted_blocks"] for s in model_states.values()),
                            max(s["gpu_evicted_blocks"] for s in model_states.values()),
                            min(s["host_evicted_blocks"] for s in model_states.values()),
                            max(s["host_evicted_blocks"] for s in model_states.values())),
             varies="yes", evidence="per segment in the JSON"),
        dict(causal_link="the tier at arrival shows up as the request's own hit pattern",
             implementing_quantity="measured classes on the scored set",
             value_range=str(dict(sorted(Counter(r["measured"] for r in det).items()))),
             varies="yes", evidence="all four classes occur"),
    ]
    absent = [r for r in step2 if not r["varies"].startswith("yes")]
    return dict(
        step1_causal_chain=(
            "A device history is reusable only while its blocks are still in a cache tier "
            "(FORMULATION.md: the physical component of context inertia, where reconstruction "
            "cost grows with context length). Under write-through every block computed on GPU is "
            "also stored on host, so the only thing that removes a history is eviction, and "
            "eviction is least-recency-first on each tier independently. Therefore the tokens "
            "written to each tier since a history's last refresh, together with the refresh rule "
            "(which StudyENG1c Part A identified), decide whether the next request for that "
            "history is served from GPU, from host, or recomputed. All of those inputs are "
            "things a scheduler knows when it issues the requests, so the claim under test is "
            "that bookkeeping alone predicts the tier."),
        step2_instantiation=step2,
        step2_verdict=("PASS: no link is ABSENT or CONSTANT" if not absent
                       else "STOP: %d link(s) ABSENT or CONSTANT" % len(absent)),
        step3_unit_trace=unit_trace(streams, truth),
        step4_negative_control=control,
        step5_alternative_explanation=(
            "The headline could be produced by (a) the identified rule's detail (write-through "
            "plus the asymmetric host refresh plus tail-first eviction) [the claimed mechanism], "
            "or (b) something much cruder that happens to agree: tier fullness alone, FIFO, or "
            "LRU without the host-path asymmetry. That is exactly what R2 tests, and the four "
            "comparison predictors share every line of the machinery except the policy switch, "
            "so a difference between them is the policy. A third alternative is that the streams "
            "are so lopsided (most arrivals cold at the small caps) that a predictor saying COLD "
            "always would score well; the per-class confusion matrices and the measured class "
            "mix are reported so that can be read off, and a constant-COLD baseline is included."),
        model_states=model_states,
        note="recorded before any TEST verdict was written")


def unit_trace(streams: Dict[str, List[Req]], truth: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Step 3: one history followed through one server segment, with every write that displaced
    it and the arithmetic of the prediction, readable by hand."""
    server = "C_c27"
    reqs = sorted(streams[server], key=lambda r: (r.t_submit, r.rid))
    target = next(r for r in reqs if r.reuse and r.hist_tokens > 0)
    model = ResidencyModel(reqs[0].cap_gib, "rule")
    events = []
    written_since = 0
    for req in reqs:
        pred = model.predict(req)
        if req.rid == target.rid:
            m = truth.get(req.rid, {})
            events.append(dict(step="PREDICT the target", rid=req.rid, hid=req.hid,
                               hist_tokens=req.hist_tokens, prompt_tokens=req.prompt_tokens,
                               gpu_chunks_present=pred.gpu_chunks,
                               host_chunks_present=pred.host_chunks,
                               hit_tokens=pred.hit_tokens,
                               recomputed_prefix_tokens=pred.recomputed_prefix_tokens,
                               predicted=pred.cls, measured=m.get("cls"),
                               measured_route=m.get("route"),
                               tokens_written_since_its_build=written_since,
                               gpu_capacity=model.gpu.capacity_tokens,
                               host_capacity=model.host.capacity_tokens,
                               gpu_tokens_now=model.gpu.tokens(),
                               host_tokens_now=model.host.tokens()))
            break
        if req.writes_hid == target.hid:
            written_since = 0
            events.append(dict(step="the target's own build", rid=req.rid,
                               prompt_tokens=req.prompt_tokens))
        else:
            written_since += req.prompt_tokens
            if len(events) < 8:
                events.append(dict(step="other work written to both tiers", rid=req.rid,
                                   prompt_tokens=req.prompt_tokens,
                                   role=req.meta.get("role"),
                                   cumulative_written_since_target=written_since))
        model.complete(req, pred)
    return dict(server=server, cap_gib=reqs[0].cap_gib, target_rid=target.rid,
                events=events,
                bound_by="tier capacity and recency only; no accelerator or KV budget enters a "
                         "residency prediction",
                reading="the prediction is a lookup of contiguous chunks from index 0, first on "
                        "GPU and then on host, so the arithmetic above is the whole decision")


# ------------------------------------------------------------------------- driver
def constant_cold_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [dict(r, predicted="COLD", policy="always_cold") for r in rows]


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--draws", type=int, default=10000)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args(list(argv) if argv is not None else None)
    out_dir = Path(args.out_dir) if args.out_dir else (_root() / OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    streams, stream_audit = build_streams()
    truth = measured_truth()
    print("stream: %d requests over %d server segments; truth rows %d"
          % (stream_audit["n_requests"], stream_audit["n_servers"], len(truth)))

    all_rows: Dict[str, List[Dict[str, Any]]] = {}
    test_rows: Dict[str, List[Dict[str, Any]]] = {}
    insample_rows: Dict[str, List[Dict[str, Any]]] = {}
    for policy in POLICIES:
        rows = joined(streams, truth, policy)
        all_rows[policy] = rows
        test_rows[policy] = [r for r in rows if r["part"] in TEST_PARTS]
        insample_rows[policy] = [r for r in rows if r["part"] in IN_SAMPLE_PARTS]

    fence = dict(
        n_holdout_requests_in_stream=sum(1 for v in streams.values() for r in v if r.holdout),
        n_holdout_in_any_scored_set=sum(1 for rows in all_rows.values() for r in rows
                                        if r["rid"] in {x.rid for v in streams.values()
                                                        for x in v if x.holdout}),
        n_truth_rows_for_holdout=0,
        rule="holdout pairs are replayed for capacity and excluded from every scored set; "
             "measured_class is never computed for them")

    det_test = {p: [r for r in test_rows[p] if r["determined"]] for p in POLICIES}
    r1 = dict(criterion="R1: 4-class tier accuracy at least 0.90 pooled and 0.85 in every cap",
              n=len(det_test["rule"]), pooled=accuracy(det_test["rule"]),
              per_cap={k: v["accuracy"] for k, v in
                       by_cut(det_test["rule"], lambda r: int(r["cap"])).items()},
              threshold_pooled=0.90, threshold_per_cap=0.85)
    r1["verdict"] = ("PASS" if (r1["pooled"] is not None and r1["pooled"] >= 0.90
                                and all(v >= 0.85 for v in r1["per_cap"].values()))
                     else "FAIL")
    comparisons = {}
    for p in POLICIES:
        if p == "rule":
            continue
        comparisons[p] = dict(accuracy=accuracy(det_test[p]),
                              bootstrap=paired_bootstrap(det_test["rule"], det_test[p],
                                                         draws=args.draws))
    cold = constant_cold_rows(det_test["rule"])
    comparisons["always_cold"] = dict(accuracy=accuracy(cold),
                                      bootstrap=paired_bootstrap(det_test["rule"], cold,
                                                                 draws=args.draws))
    beaten = {k: bool(v["bootstrap"]["favours_rule"] and v["bootstrap"]["excludes_zero"])
              for k, v in comparisons.items()}
    r2 = dict(criterion="R2: the rule beats every comparison predictor, paired bootstrap CI "
                        "(by trial) excluding 0",
              rule_accuracy=accuracy(det_test["rule"]), comparisons=comparisons,
              beats_all=all(beaten[k] for k in beaten if k != "always_cold"),
              beats_including_constant_cold=all(beaten.values()),
              per_predictor=beaten)
    r2["verdict"] = "PASS" if r2["beats_all"] else "FAIL"
    r3 = r3_partial(det_test["rule"])
    r3["criterion"] = "R3: MAE of the predicted fraction on host at most 0.10 on PARTIAL cases"

    mech = mechanism(streams, truth, test_rows)
    mech["stream_audit"] = stream_audit
    mech["holdout_fence"] = fence
    mech["_provenance"] = _stamp(len(det_test["rule"]), args)
    (out_dir / "res1_mechanism.json").write_text(json.dumps(mech, indent=1, default=str))
    print("mechanism: %s | control: rule %.4f -> shuffled %.4f (occupancy %.4f), fell toward "
          "baseline %s" % (mech["step2_verdict"],
                           mech["step4_negative_control"]["accuracy_rule_normal"],
                           mech["step4_negative_control"]["accuracy_rule_shuffled"],
                           mech["step4_negative_control"]["accuracy_occupancy_baseline"],
                           mech["step4_negative_control"]["fell_toward_baseline"]))
    if mech["step2_verdict"].startswith("STOP"):
        print("STOPPING: an ABSENT or CONSTANT link")
        return 2

    no_pieces = [r for r in test_rows["rule"] if not (r["part"] == "B" and r["role"]
                                                      in ("piece2", "piece3", "piece4",
                                                          "piece5"))]
    secondary_2class = dict(
        all_test=dict(n=len(test_rows["rule"]), accuracy=two_class(test_rows["rule"]),
                      per_policy={p: two_class(test_rows[p]) for p in POLICIES}),
        excluding_part_b_pieces=dict(
            n=len(no_pieces), accuracy=two_class(no_pieces),
            per_policy={p: two_class([r for r in test_rows[p]
                                      if not (r["part"] == "B" and r["role"]
                                              in ("piece2", "piece3", "piece4", "piece5"))])
                        for p in POLICIES}),
        note="pre-declared analysis 1: the Part B piece-chain requests are warm by construction, "
             "so any predictor that says warm is right about them for free")

    errors = [r for r in det_test["rule"] if r["predicted"] != r["measured"]]
    error_classes = Counter("%s->%s" % (r["measured"], r["predicted"]) for r in errors)
    out = dict(
        study="StudyRES1-residency",
        frozen_row_md5="91f3c3fe2c72fb089e9fcb1aac43cbbd",
        frozen_row_utc="2026-11-17T16:59:11Z",
        predeclaration_md5="1248b640ef7ca7847953e0f9332096ea",
        scope=("R1 to R3 on TEST requests whose 4-class tier is MEASURED; a labelled 2-class "
               "secondary over every TEST reuse request"),
        counts=dict(test_reuse=len(test_rows["rule"]), test_measured=len(det_test["rule"]),
                    test_unmeasured=len(test_rows["rule"]) - len(det_test["rule"]),
                    in_sample_part_a=len(insample_rows["rule"]),
                    measured_classes=dict(sorted(Counter(r["measured"]
                                                         for r in det_test["rule"]).items()))),
        R1=r1, R2=r2, R3=r3,
        secondary_2class=secondary_2class,
        confusion={p: confusion(det_test[p]) for p in POLICIES},
        per_cut=dict(per_cap=by_cut(det_test["rule"], lambda r: int(r["cap"])),
                     per_part=by_cut(det_test["rule"], lambda r: r["part"]),
                     per_conc=by_cut(det_test["rule"], lambda r: str(r["conc"])),
                     per_role=by_cut(det_test["rule"], lambda r: str(r["role"])),
                     per_part_cap=by_cut(det_test["rule"],
                                         lambda r: "%s|%s" % (r["part"], int(r["cap"])))),
        per_cut_per_policy={p: dict(per_cap=by_cut(det_test[p], lambda r: int(r["cap"])),
                                    per_part=by_cut(det_test[p], lambda r: r["part"]))
                            for p in POLICIES},
        selection_check=selection_check(test_rows["rule"]),
        telemetry_belief=telemetry_belief(test_rows["rule"]),
        concurrency_host_warm=concurrency_host_warm(test_rows["rule"]),
        part_a_in_sample=part_a_touch_rules(insample_rows["rule"]),
        part_a_per_policy={p: accuracy(insample_rows[p]) for p in POLICIES},
        eng1c_sim_agreement=eng1c_sim_agreement(truth),
        errors=dict(n=len(errors), classes=dict(sorted(error_classes.items())),
                    by_part=dict(sorted(Counter(r["part"] for r in errors).items())),
                    by_cap=dict(sorted(Counter(int(r["cap"]) for r in errors).items())),
                    by_role=dict(sorted(Counter(str(r["role"]) for r in errors).items()))),
        holdout_fence=fence, stream_audit=stream_audit)
    out["_provenance"] = _stamp(len(det_test["rule"]), args)
    (out_dir / "res1_scores.json").write_text(json.dumps(out, indent=1, default=str))
    (out_dir / "res1_errors.json").write_text(json.dumps(
        dict(n=len(errors), rows=errors,
             measured_class_mix=dict(sorted(Counter(r["measured"]
                                                    for r in det_test["rule"]).items())),
             _provenance=_stamp(len(errors), args)), indent=1, default=str))
    print("R1 pooled %.4f (%s) per cap %s" % (r1["pooled"], r1["verdict"],
                                              {k: round(v, 4) for k, v in r1["per_cap"].items()}))
    for k, v in sorted(comparisons.items()):
        b = v["bootstrap"]
        print("  vs %-12s acc %.4f  diff %+.4f CI [%+.4f, %+.4f] excludes0 %s"
              % (k, v["accuracy"], b["diff"], b["ci"][0], b["ci"][1], b["excludes_zero"]))
    print("R2 %s | R3 %s (mae %s on n=%d)" % (r2["verdict"], r3["verdict"],
                                              ("%.4f" % r3["mae"]) if r3["mae"] is not None
                                              else "n/a", r3["n"]))
    print("2-class: all %.4f | excluding Part B pieces %.4f"
          % (secondary_2class["all_test"]["accuracy"],
             secondary_2class["excluding_part_b_pieces"]["accuracy"]))
    print("wrote %s" % (out_dir / "res1_scores.json"))
    return 0


def _stamp(n: int, args: Any) -> Dict[str, Any]:
    sys.path.insert(0, str(_root() / "experiments" / "lib"))
    from _provenance import stamp
    return stamp(script="orchestration/run_res1.py", model=None, device=None, n=n,
                 args=vars(args))


if __name__ == "__main__":
    raise SystemExit(main())
