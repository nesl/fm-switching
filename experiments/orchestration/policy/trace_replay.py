"""T0's replay: reconstruct each recorded StudyENG1 Part C trial and each StudyENG1b trial from
the committed logs, and predict what the measurement measured.

PART C. A Part C trial is a PAIR of runs over the same 10-second background trace, one WITHOUT
the candidate action and one WITH it. The measured quantity is the TOTAL IMPOSED DELAY on all
other requests: the sum, over background requests matched by index, of TTFT(with) minus
TTFT(without). T0 therefore predicts the SAME difference the same way (ambiguity A35): the
trial's actual recorded arrivals, sizes and timings are replayed through `eng1_engine.EngineSim`
twice, once with the action's recorded request(s) inserted at their recorded instant and once
without, and the prediction is the difference of the two simulated sums. Any error common to
both arms cancels in the prediction exactly as it cancels in the measurement.

Nothing is fitted here and nothing is read from a Part C or HOLDOUT measurement except the
INPUTS: who arrived when, how big the body was, how many prompt tokens, how many were cached,
how many of those came from the HOST tier (StudyPOL4-engine, see EXTERNAL_TOKENS_COUNTER below),
and how many output tokens were produced. The measured TTFTs are read only to be compared
against.

PART C, WHAT COUNTS AS "ALL OTHER REQUESTS". This is a DEFINITION and it was wrong in the first
implementation; CLAUDE.md's consistency check 1 caught it and the fix is recorded here because a
name used with two definitions is the failure this repository has been burned by twice.

StudyENG1 section 9's published per-cell table counts ONLY THE EPISODIC BACKGROUND STREAM. In the
W25 cells the trace also carries 8 warm sessions' appends and escalations; those requests run, and
they occupy the engine, but they are NOT in the sum the report publishes. Summing over them as
well reproduces none of the five W25 medians, and summing over the episodic stream alone
reproduces all five exactly (16.8934 against the published 16.900 for W25 mono11k, 0.4406 against
0.440 for W25 piece2048, 0.1360 against 0.140, 0.0642 against 0.060, 0.0536 against 0.050). The
24 non-W25 cells are unaffected, because their background IS the episodic stream, and all 24
reproduce the published median to the published precision.

`COMPARED_KINDS` is therefore the set summed over and defaults to the episodic stream, which is
StudyENG1's published quantity. Every other kind stays in the SIMULATION, because the warm
sessions really do take engine time; what changes is only which requests enter the sum.

PART C, SETUP REQUESTS. A trial's `build` rows (the cached prefix a piece runs on, the context an
append runs on, the history a host reload runs on, and the fillers that evict it) run BEFORE the
trace starts and complete before it. They are replayed as part of neither arm's timeline; what
they leave behind is the `cached_tokens` the recorded action row carries, which is the input the
simulator needs. Any setup row that is NOT finished before the trace start is reported, because
then the trial could not be reconstructed this way.

ENG1b. A trial is one build, one gap with recorded KV demand, and one resume. The prediction is
MECHANISTIC and uses no parameter fitted on ENG1b: the KV pool of `kvpool.KVPool` is given the
server's pool size and the built prefix as an UNREFERENCED entry, the recorded allocation of
other work during the gap is applied through `KVPool.allocate`, and the predicted loss is read
off the pool. StudyENG1b's own measured staircase is NOT used (`kvpool.eng1b_long_gap_curve`
exists for long gaps and is deliberately not called here).
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .eng1_engine import EngineSim, SimRequest, StepModel
from .kvpool import KVPool, PrefixEntry

BACKGROUND_KINDS = ("episodic", "warm_append", "warm_escalation")
# The requests the imposed-delay SUM runs over: StudyENG1 section 9's published quantity. The
# other background kinds stay in the simulation and out of the sum (see the module docstring).
COMPARED_KINDS = ("episodic",)
ACTION_KINDS = ("inject",)
SETUP_KINDS = ("build",)

PART_C_PATH = "results/cost/study_eng1/eng1_partC_requests_h100nvl.jsonl"
HOLDOUT_SPLIT_PATH = "results/cost/study_eng1/eng1_holdout_split.json"
ENG1B_RESULTS_PATH = "results/cost/study_eng1b/eng1b_results.json"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


# --------------------------------------------------------------------------- Part C loading
@dataclass
class Arm:
    mode: str
    t0_trace: float
    background: List[Dict[str, Any]] = field(default_factory=list)
    action: List[Dict[str, Any]] = field(default_factory=list)
    setup: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Trial:
    load: str
    action: str
    trial: int
    holdout: bool
    t_inj_rel: float
    arms: Dict[str, Arm] = field(default_factory=dict)
    # per arm, the run's external_kv_transfer tokens that could NOT be attributed to the action
    # (the W25 cells, where the 8 warm sessions produce host hits of their own in both arms)
    external_unattributed: Dict[str, int] = field(default_factory=dict)

    def cell(self) -> str:
        return "%s|%s" % (self.load, self.action)

    def key(self) -> str:
        return "%s|%s|%d" % (self.load, self.action, self.trial)


def _n_images(row: Dict[str, Any]) -> int:
    """Images the request carries. `n_frames` where the row records it; otherwise the NEW prompt
    tokens at the committed 90 tokens per D2 frame, which is StudyENG1's own frame definition."""
    if row.get("n_frames") is not None:
        return int(row["n_frames"])
    new = max(int(row.get("prompt_tokens", 0)) - int(row.get("cached_tokens", 0) or 0), 0)
    if row.get("kind") == "warm_escalation":
        return 0
    return max(int(round(new / 90.0)), 1 if new > 0 else 0)


def _sim_request(row: Dict[str, Any], t0: float, tag: str) -> SimRequest:
    return SimRequest(
        rid=str(row.get("rid") or "%s:%s" % (tag, row.get("idx"))),
        t_submit=float(row["t_submit"]) - t0,
        prompt_tokens=int(row.get("prompt_tokens", 0) or 0),
        cached_tokens=int(row.get("cached_tokens", 0) or 0),
        body_mb=float(row.get("body_mb", 0.0) or 0.0),
        n_images=_n_images(row),
        out_tokens=max(int(row.get("completion_tokens", 1) or 1), 1),
        external_cached_tokens=int(row.get("_external_cached_tokens", 0) or 0),
        tag=tag)


# StudyPOL4-engine term (a) needs to know how many of a request's cached tokens came from the
# HOST tier rather than the GPU. That is RECORDED, not inferred: each Part C run's summary row
# carries the engine's own `prompt_tokens_by_source|external_kv_transfer` counter over the run.
#
# The counter is PER RUN, not per request, so it may only be attributed to the action where
# nothing else in the trace could have produced it. Two conditions must BOTH hold, and they are
# checked per trial rather than assumed:
#   (1) the arm's counter equals the arm's action rows' cached tokens, within the 32-token
#       prefix-chaining tolerance StudyENG1 used throughout, and
#   (2) the OTHER arm's counter is zero, so no background or warm request reloads from host.
# On the committed record that selects the hostreload cells and nothing else: outside them the
# counter is zero everywhere except the five W25 cells, where it is the 8 warm sessions' OWN
# host hits (19k to 50k tokens, present in both arms and present even where the action has no
# cached tokens at all). Those trials are therefore left UNATTRIBUTED and charged nothing, which
# is recorded as a limitation: the warm sessions' reloads are real engine work in BOTH arms of a
# W25 pair, so they largely cancel in the paired difference the criterion is computed on, but
# the model does not charge them.
EXTERNAL_TOKENS_COUNTER = "prompt_tokens_by_source_total|external_kv_transfer"
EXTERNAL_TOLERANCE_TOKENS = 32


def load_part_c_trials(path: Any = None) -> List[Trial]:
    """Every Part C trial, FIT and HOLDOUT alike, as reconstructed pairs. Loading does not look
    at any measured TTFT; selecting the split is the caller's job and the harness guards it."""
    p = Path(path) if path is not None else (_repo_root() / PART_C_PATH)
    buckets: Dict[Tuple[str, str, int], Trial] = {}
    external: Dict[Tuple[str, str, int, str], int] = {}
    with open(p) as fh:
        for line in fh:
            row = json.loads(line)
            kind = row.get("kind")
            if kind == "run_summary":
                md = row.get("metrics_delta") or {}
                if row.get("mode") in ("with", "without"):
                    external[(row["load"], row["action"], int(row["trial"]),
                              row["mode"])] = int(md.get(EXTERNAL_TOKENS_COUNTER, 0) or 0)
                continue
            if kind == "pair_check":
                continue
            mode = row.get("mode")
            if mode not in ("with", "without"):
                continue
            k = (row["load"], row["action"], int(row["trial"]))
            tr = buckets.get(k)
            if tr is None:
                tr = Trial(load=row["load"], action=row["action"], trial=int(row["trial"]),
                           holdout=bool(row.get("holdout")),
                           t_inj_rel=float(row.get("t_inj_rel") or 0.0))
                buckets[k] = tr
            arm = tr.arms.get(mode)
            if arm is None:
                arm = Arm(mode=mode, t0_trace=float(row.get("t0_trace") or 0.0))
                tr.arms[mode] = arm
            if row.get("t0_trace") and not arm.t0_trace:
                arm.t0_trace = float(row["t0_trace"])
            if kind in SETUP_KINDS:
                arm.setup.append(row)
            elif kind in ACTION_KINDS:
                arm.action.append(row)
            elif kind in BACKGROUND_KINDS:
                arm.background.append(row)
    for (load, action, trial, mode), ext in sorted(external.items()):
        trial_obj = buckets.get((load, action, trial))
        if trial_obj is None or mode not in trial_obj.arms or ext <= 0:
            continue
        other = "without" if mode == "with" else "with"
        if external.get((load, action, trial, other), 0) != 0:
            trial_obj.external_unattributed[mode] = ext
            continue
        rows = sorted(trial_obj.arms[mode].action, key=lambda r: (r.get("idx") or 0))
        cached = sum(int(r.get("cached_tokens", 0) or 0) for r in rows)
        if abs(cached - ext) > EXTERNAL_TOLERANCE_TOKENS:
            trial_obj.external_unattributed[mode] = ext
            continue
        left = ext
        for row in rows:
            take = min(left, int(row.get("cached_tokens", 0) or 0))
            row["_external_cached_tokens"] = take
            left -= take
    return [buckets[k] for k in sorted(buckets)]


def _bg_key(row: Dict[str, Any]) -> Tuple[str, Any]:
    return (str(row.get("kind")), row.get("idx") if row.get("idx") is not None
            else (row.get("session"), row.get("session_t")))


def measured_imposed_delay_s(trial: Trial,
                             kinds: Sequence[str] = COMPARED_KINDS) -> Dict[str, Any]:
    """StudyENG1 section 9's own quantity: the sum over the EPISODIC background requests, matched
    by index, of TTFT(with) minus TTFT(without). See the module docstring for why the warm
    sessions of the W25 cells are simulated but not summed over."""
    w = {_bg_key(r): r for r in trial.arms["with"].background if r.get("kind") in kinds}
    o = {_bg_key(r): r for r in trial.arms["without"].background if r.get("kind") in kinds}
    shared = sorted(set(w) & set(o), key=lambda k: str(k))
    per = []
    total = 0.0
    for k in shared:
        a, b = w[k].get("ttft_s"), o[k].get("ttft_s")
        if a is None or b is None:
            continue
        d = float(a) - float(b)
        total += d
        per.append(dict(key=str(k), with_s=float(a), without_s=float(b), delta_s=d))
    return dict(total_s=total, n_matched=len(per), n_with=len(w), n_without=len(o), per=per,
                compared_kinds=list(kinds))


def measured_action_completion_s(trial: Trial) -> Optional[float]:
    """The action's OWN completion time: for a single action its latency, and for a burst the
    time from the first action's submit to the last one's completion."""
    acts = trial.arms["with"].action
    if not acts:
        return None
    subs = [float(a["t_submit"]) for a in acts if a.get("t_submit") is not None]
    ends = [float(a["t_end"]) for a in acts if a.get("t_end") is not None]
    if not subs or not ends:
        return None
    return max(ends) - min(subs)


def _arm_requests(arm: Arm, include_action: bool) -> List[SimRequest]:
    out = [_sim_request(r, arm.t0_trace, "background") for r in arm.background]
    if include_action:
        out += [_sim_request(r, arm.t0_trace, "action") for r in arm.action]
    return out


def setup_overlap_report(trial: Trial) -> Dict[str, Any]:
    """Every setup request must finish before the trace starts, or the trial cannot be
    reconstructed from the record the way T0 reconstructs it. This reports the violation rather
    than hiding it."""
    rows = []
    for mode, arm in sorted(trial.arms.items()):
        for r in arm.setup:
            end = r.get("t_end")
            if end is None:
                rows.append(dict(mode=mode, rid=r.get("rid"), role=r.get("role"),
                                 reason="no completion time recorded"))
                continue
            if float(end) > arm.t0_trace + 1e-9:
                rows.append(dict(mode=mode, rid=r.get("rid"), role=r.get("role"),
                                 overlap_s=float(end) - arm.t0_trace))
    return dict(ok=not rows, offenders=rows)


def predict_trial(trial: Trial, sim: EngineSim,
                  kinds: Sequence[str] = COMPARED_KINDS) -> Dict[str, Any]:
    """Predict the imposed delay and the action's completion time for one Part C trial.

    The with-arm and the without-arm are each replayed from their OWN recorded arrival times, so
    the prediction uses the arrivals that actually happened in each arm, and the difference is
    taken over the background requests the two arms share, which is the measured quantity."""
    for mode in ("with", "without"):
        if mode not in trial.arms:
            raise KeyError("trial %s has no %r arm; it cannot be reconstructed" % (trial.key(),
                                                                                  mode))
    res_with = sim.run(_arm_requests(trial.arms["with"], include_action=True))
    res_without = sim.run(_arm_requests(trial.arms["without"], include_action=False))
    pw = res_with["per_request"]
    po = res_without["per_request"]
    w_rows = {_bg_key(r): r for r in trial.arms["with"].background
              if r.get("kind") in kinds}
    o_rows = {_bg_key(r): r for r in trial.arms["without"].background
              if r.get("kind") in kinds}
    shared = sorted(set(w_rows) & set(o_rows), key=lambda k: str(k))
    total = 0.0
    n = 0
    per = []
    for k in shared:
        a = pw.get(str(w_rows[k].get("rid")), {}).get("ttft_s")
        b = po.get(str(o_rows[k].get("rid")), {}).get("ttft_s")
        if a is None or b is None:
            continue
        d = float(a) - float(b)
        total += d
        n += 1
        per.append(dict(key=str(k), with_s=float(a), without_s=float(b), delta_s=d))
    acts = trial.arms["with"].action
    comp = None
    if acts:
        subs, ends = [], []
        for r in acts:
            pr = pw.get(str(r.get("rid")))
            if pr is None:
                continue
            subs.append(float(r["t_submit"]) - trial.arms["with"].t0_trace)
            ends.append(pr.get("t_end") if pr.get("t_end") is not None else pr.get("t_first"))
        ends = [e for e in ends if e is not None]
        if subs and ends:
            comp = max(ends) - min(subs)
    return dict(predicted_delay_s=total, n_matched=n, compared_kinds=list(kinds),
                predicted_action_completion_s=comp,
                n_steps_with=res_with["n_steps"], n_steps_without=res_without["n_steps"],
                unfinished=res_with["unfinished"] + res_without["unfinished"], per=per)


# --------------------------------------------------------------------------- ENG1b
FULL_RESIDENT_TOLERANCE_TOKENS = 32    # StudyENG1b section 7 check 4, the chaining tolerance


def loss_class(lost_tokens: int, prefix_tokens: int,
               tol: int = FULL_RESIDENT_TOLERANCE_TOKENS) -> str:
    """StudyENG1b's own three classes, under its own definitions: "fully resident" is local hits
    at or above prefix minus the 32-token chaining tolerance, and "lost" is prefix minus local
    hits."""
    lost = max(int(lost_tokens), 0)
    pref = max(int(prefix_tokens), 1)
    if lost <= tol:
        return "none"
    if lost >= pref - tol:
        return "total"
    return "partial"


def load_eng1b_trials(path: Any = None) -> Dict[str, Any]:
    p = Path(path) if path is not None else (_repo_root() / ENG1B_RESULTS_PATH)
    return json.loads(Path(p).read_text())


def predict_eng1b_trial(trial: Dict[str, Any], kv_capacity_tokens: int,
                        pressure_field: str = "alloc_before_sched") -> Dict[str, Any]:
    """MECHANISTIC prediction of prefix loss for one StudyENG1b trial.

    The pool is given the server's capacity and the built prefix as the single UNREFERENCED
    entry, which is the state A6 describes between pieces. The recorded allocation of other work
    during the gap is then applied, and the predicted loss is whatever the pool's own
    bookkeeping frees. No ENG1b-fitted number enters: not the staircase, not a threshold, not a
    bin.

    `pressure_field` is `alloc_before_sched` (StudyENG1b's version (ii), the allocation the
    eviction actually sees) or `alloc_before_resume` (version (i), as pre-registered)."""
    prefix = int(trial["prefix"])
    alloc = int(trial.get(pressure_field) or 0)
    pool = KVPool(capacity_tokens=int(kv_capacity_tokens))
    pid = "prefix:eng1b"
    pool.put(pid, prefix, 0.0, referenced=False)
    res = pool.allocate("other_work", alloc, 1.0)
    lost = int(res["freed"].get(pid, 0))
    frac = lost / float(max(prefix, 1))
    return dict(predicted_lost_tokens=lost, predicted_fraction_lost=frac,
                predicted_class=loss_class(lost, prefix),
                predicted_head_tokens=pool.entries[pid].head_tokens() if pid in pool.entries
                else 0,
                free_pool_tokens=int(kv_capacity_tokens) - prefix,
                allocated_tokens=alloc, pressure_field=pressure_field,
                basis="kvpool.KVPool bookkeeping only: capacity, the unreferenced prefix, the "
                      "free-block order and the recorded allocation; tail-first within the "
                      "prefix (StudyENG1b's partial losses keep the leading tokens)")
