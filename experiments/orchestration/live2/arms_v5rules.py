#!/usr/bin/env python3
"""`v5-rules`: the RULES-ONLY v5 arm. Its own labelled arm, never mixed with full v5.

WHY THIS ARM EXISTS AND WHAT IT IS NOT. D151 (6) gates any live v5 run on a cost-model
recalibration; D154 (2) sets `MARGIN_CF` from that gate's held-out p90 error and forbids any v5
cell before it is set. The gate does not pass (`reports/policy_v5_assessment.md` sections A.1 and
C), so full v5 cannot run. A RULES-based v5 makes no counterfactual prediction, needs no margin
and therefore needs no gate pass. That is the whole of this arm's claim to run.

  * BASE: `hybrid-F-lhreq-noc3`, taken from the committed `hybrid/hybrid_arm.py::CONFIGS` and not
    re-derived (D152 (2), D154 (3), spec v5 section 4). Every request decision, every feasibility
    decline and every representation is the base's.
  * ADDED, and it is the ONLY added channel: WARM-AHEAD AS A RULE. Every robot session the cloud
    holds uploaded frames for is prefilled onto its append-only history, at lowest priority,
    yielding to deadline work, through session C's `engine_actions.plan_warm_ahead` (D150 STATE
    lever 1, spec v5 section 8). No prefill logic is written here.
  * NOT ADDED, deliberately: no counterfactual, no planner, no latest-safe-start, no `MARGIN_CF`,
    no value reader, no deficit weighting, no KEEP_GPU_WARM, no OFFLOAD_TO_HOST, no EVICT, no
    reload, no hold-back, no slicing of a deadline request. Needing `MARGIN_CF` would mean this
    had strayed into full v5.

TWO THINGS THAT ARE NOT IN THIS FILE BECAUSE THEY ARE NOT THE ARM'S.

  1. EP-G dashcam bodies are a property of the TRACE and the coordinator (D153, `eeea7e0`,
     `--dashcam-format epg`), not of any arm, and the request digest is identical across arms on
     every shared opportunity (`reports/study_epg_bodies.md` proof (b)). So `v5-rules` runs on
     EP-G by being given an EP-G trace and changes nothing to get it. The EP-G accelerator charge
     is the episode's NEW tokens, `42 + 338 x frames carrying bytes`, which is the committed
     convention in `coordinator.py` and is kept here by not touching it.
  2. PER-FRAME ROBOT UPLOAD (D154 (4)) is likewise a trace property, landed at `34a4af0` behind
     `--robot-upload per-frame` with `batch-30s` the default. `v5-rules` needs NO change to pick
     it up: `trace.ROBOT_UPLOAD_NOTE` states the record kind and fields are unchanged "so the
     emulator, the coordinator, `cstate` and every arm need no change", and the warm-ahead rule
     asks for every candidate session every epoch while `_advance_build` issues a piece only for
     frames newly uploaded, so a finer grain makes the same rule fire more often. Measured:
     `perframe_pickup()` gives 1,163 prefills under per-frame against 330 under batch-30s on the
     same cell, 3.52x, agreeing with the committed 3.27x measured on `warm-all-lru`. The contract
     is passed to the trace generator ONLY if that generator takes it, so this file still runs on
     a tree where the switch does not exist. A cell at the default is labelled `upload-30s`.

WHY ROBOT SESSIONS ONLY, stated because a wider candidate set would silently change what the
count means. The rule is "prefill every uploaded robot frame onto its device's append-only
history" and only robot devices have such a history: a dashcam's episode context is built by the
monitoring request itself under EP-G, and a single-shot session's one image is captured AT
QUESTION TIME (`fleet/trace.py`, the SINGLE SHOT block: one `history_batch` carrying the single
image, at `t_q`), so there is nothing to warm ahead of its question and a MATERIALIZE naming it
would be reactive warming counted as warm-ahead. `engine_actions.plan_warm_ahead` already
excludes any session with a pending question for the same reason.

THE ASK AND THE DECISION ARE DIFFERENT NUMBERS AND ARE NEVER ADDED. `warm_ahead_emitted` counts
MATERIALIZE actions emitted, one per candidate session per epoch; most are no-ops inside
`coordinator._advance_build` (`new_refs` empty -> None). The characteristic DECISION is the
prefill the coordinator ISSUED, one `release_piece` / `release_whole` row each, read off the
decision log. `proofs()` reports the issued count as the headline and the ask count beside it,
labelled, and never sums them.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for _p in (HERE, HERE / "hybrid", HERE / "fleet",
           REPO / "experiments/orchestration/baselines",
           REPO / "experiments/orchestration/baselines/reconstructed",
           REPO / "experiments/orchestration/sim", REPO / "experiments/lib",
           REPO / "experiments/orchestration"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import engine_actions as EA                                            # noqa: E402
from interface import Action, Observation                              # noqa: E402

V5RULES_VERSION = "v5-rules-1.0"
V5RULES_BASE = "hybrid-F-lhreq-noc3"


class V5RulesArm:
    """The base plus one channel. Every live2 hook is delegated to the committed base arm."""

    def __init__(self, name: str = "v5-rules", warm_ahead: bool = True,
                 yield_to_deadline: bool = True,
                 slice_tokens: Optional[int] = EA.WARM_AHEAD_SLICE_TOKENS) -> None:
        from hybrid.hybrid_arm import CONFIGS, HybridArm
        if V5RULES_BASE not in CONFIGS:
            raise KeyError("committed base config %r is absent from hybrid_arm.CONFIGS"
                           % (V5RULES_BASE,))
        # The committed config, taken whole. Not re-derived and not edited: a base assembled
        # switch by switch here would drift from the frozen policy without anything saying so.
        self._base = HybridArm(name=V5RULES_BASE, **CONFIGS[V5RULES_BASE])
        self.name = name
        self.warm_ahead = bool(warm_ahead)
        self.yield_to_deadline = bool(yield_to_deadline)
        self.slice_tokens = None if slice_tokens is None else int(slice_tokens)
        self.arm_version = V5RULES_VERSION
        self.live2_source = ("hybrid/hybrid_arm.py::HybridArm(CONFIGS['%s']) AS COMMITTED, plus "
                             "live2/engine_actions.py::plan_warm_ahead (W2 discipline)"
                             % V5RULES_BASE)
        self.stats: Counter = Counter()
        self._roster: Dict[str, Any] = {}

    # ---- delegation, identical in shape to arms_warmall.py and hybrid/hybrid_arm.py -----------
    def __getattr__(self, k):
        return getattr(self.__dict__["_base"], k)

    def __call__(self, obs: Observation) -> Action:
        return self._base.__class__.__call__(self, obs)

    def live2_roster(self, roster: Dict[str, Any]) -> None:
        """The base READS the roster (C1 and C2 take dashcam deadlines from it), unlike b7, so it
        is forwarded unchanged as well as kept. Forwarding it is what makes the `-off` control
        byte-identical to the base rather than merely close to it."""
        self._roster = dict(roster or {})
        self._base.live2_roster(roster)

    def live2_configure(self, **kw: Any) -> None:
        self._base.live2_configure(**kw)

    def live2_describe(self) -> Dict[str, Any]:
        d = dict(self._base.live2_describe()) if hasattr(self._base, "live2_describe") else {}
        d.update(arm=self.name, arm_version=V5RULES_VERSION,
                 v5_rules=dict(base=V5RULES_BASE, warm_ahead=self.warm_ahead,
                               discipline="W2" if self.yield_to_deadline else "none",
                               slice_tokens=self.slice_tokens,
                               candidates="robot sessions only",
                               counterfactual=False, planner=False, margin_cf=None,
                               placement_steering=False,
                               engine_actions_version=EA.ENGINE_ACTIONS_VERSION),
                 source=self.live2_source)
        return d

    # ---- the one added channel ---------------------------------------------------------------
    def _candidates(self, obs: Observation) -> List[str]:
        """Every ROBOT session the cloud holds frames for, from the D100 roster.

        `session_device` and `devices[*]["type"]` are causal facts known at arrival
        (`coordinator._roster`), so nothing here reads the future.

        The arm does not try to work out which histories still have unbuilt frames, for the reason
        `arms_warmall._candidates` records: the roster carries `built_tokens_by_session` but no
        history size, so there is no local test for "fully built". It does not need one.
        `coordinator._advance_build` clamps the target to `est_tokens` and returns None when
        `new_refs` is empty, so a standing request for every robot session is a no-op for every
        session with nothing newly uploaded, and the GPU is charged only for pieces issued.
        """
        r = self._roster or {}
        devs = r.get("devices") or {}
        return sorted(sid for sid, did in (r.get("session_device") or {}).items()
                      if str((devs.get(did) or {}).get("type")) == "robot")

    def _count_release_states(self, obs: Observation, act: Action) -> None:
        """The readiness the arm BELIEVED each released recall was at, for the warm-regime split.

        Readiness is a belief, and on a PARTIALLY built history it stays `cold` while the built
        prefix is already reused on the wire as uuid references, which `coordinator.py:745-752`
        and spec v5 section 8 both state. So this split is reported as the belief it is and is NOT
        the cached-token proof; that proof is `cached_token_proof()`, on the wire form.
        """
        ready = {q.query_id: q.readiness for q in obs.recall}
        for r in act.recall:
            if r.decision != "CLOUD":
                continue
            self.stats["release_at_" + str(ready.get(r.query_id, "UNKNOWN"))] += 1

    def decide(self, obs: Observation) -> Action:
        act = self._base.decide(obs)
        self._count_release_states(obs, act)
        if not self.warm_ahead:
            return act
        plan = EA.plan_warm_ahead(obs, self._candidates(obs),
                                  slice_tokens=self.slice_tokens,
                                  yield_to_deadline=self.yield_to_deadline,
                                  targets=getattr(self._base, "_targets", None))
        self.stats["warm_ahead_wanted"] += len(plan.wanted)
        self.stats["warm_ahead_emitted"] += plan.n_warm_ahead
        self.stats["warm_ahead_unexpressible"] += len(plan.unexpressible)
        if plan.yielded:
            self.stats["warm_ahead_yielded_epochs"] += 1
        if plan.actions:
            act.sessions = list(act.sessions) + list(plan.actions)
        return act


V5RULES_ARMS = {
    "v5-rules": lambda **kw: V5RulesArm(name="v5-rules", **kw),
    # CLAUDE.md Step 4, the negative control: the same arm with the mechanism disabled. It must
    # collapse to the base BYTE-IDENTICALLY, which is stronger than "converges": if it does not,
    # what `v5-rules` measures is not the warming channel.
    "v5-rules-off": lambda **kw: V5RulesArm(name="v5-rules-off", warm_ahead=False, **kw),
    # The discipline ablation, kept constructible so the W2 claim is checkable. In NO run plan,
    # for the reason `reports/study_engine_actions.md` section 1 point 4 gives: W1's worst
    # single-shot queue wait is longer than the single-shot deadline itself.
    "v5-rules-noyield": lambda **kw: V5RulesArm(name="v5-rules-noyield",
                                                yield_to_deadline=False, **kw),
}


def register() -> None:
    """Same contract as `hybrid.register()` and `arms_warmall.register()`: put the names in
    live2's registry so `arms.make_arm(name)` builds them."""
    import arms as A
    A.ARMS.update(V5RULES_ARMS)


# ---------------------------------------------------------------- the proofs
CELL = dict(seed=4, n=16, run_s=1200.0, ratio="40:40:20",
            robot_question_set="lh_req", ss_question_set="ss2")
# The committed digest of the BASE at exactly this cell, from
# `results/orchestration/live2/frozen_test/value_reader_proofs.json` (cited in
# `reports/study_policy_v2_gate.md` section with the value-reader table). This is CLAUDE.md check
# 7's POSITIVE CONTROL: a known-good committed arm must reproduce its committed number in this
# harness. If it does not, the check is broken and not the arm, and nothing else may be read.
# RE-DERIVED 2026-11-21 ~10:05 at origin/main, per D160 addendum. The previous values
# (digest 5d3469549fead8ac, rows 13525) were recorded at 5d7c084 on 2026-11-20 16:30 and DO NOT
# reproduce at current origin, which gives d7ad8f6296049611 and 13541 rows, 16 rows more.
#
# SESSION D'S OWN UNCOMMITTED WORK IS RULED OUT, which is why this is a re-derivation and not a
# bug fix: the same digest and row count come back from a CLEAN worktree at origin/main (7dcc262)
# carrying none of session D's edits. The staleness is pre-existing on origin.
#
# WHICH COMMIT MOVED IT IS NOW ESTABLISHED BY BISECT AND FIELD DIFF, and it is benign.
#
#   eeea7e0 (11-20 18:48)  base digest 5d3469549fead8ac, 13525 rows  -> the committed value
#   f1d32c7 (11-20 19:13)  ROBOT_DEADLINE_S 5.0 -> 3.0
#   34a4af0 (11-20 19:22)  base digest d7ad8f6296049611, 13541 rows
#
# Diffing the two traces at the dry-proof cell: 14,985 records on both sides, and exactly 20 rows
# differ, in ONE field, `deadline_s`, 5.0 -> 3.0. Twenty is the robot question count at this cell.
# So the base digest moved because the ROBOT DEADLINE was tightened from 5 s to 3 s at f1d32c7,
# which is the user's own ruling D154 (1). A tighter deadline changes decisions, and those
# decisions are the 16 extra rows.
#
# BOTH COMMITS SESSION D FIRST SUSPECTED ARE INNOCENT, and their own neutrality claims stand:
#   34a4af0 per-frame upload ("at the default the trace is BYTE-IDENTICAL") - true relative to its
#           own parent 7cf9d56; session D's first bisect compared it against eeea7e0, which is 18
#           commits earlier, not its parent, so the deadline change sat inside the interval.
#   2b8714c race fix ("changes no decision") - ruled out outright, since the shift is already
#           present at 34a4af0, which predates it by about two hours.
#
# So nothing here is a defect in anyone's commit. It is a legitimate user-ordered methodological
# change whose positive control was never re-derived afterwards.
#
# This matters beyond this constant: a positive control is only a control while it reproduces, and
# a stale one fails on every arm it is applied to, which is exactly how it surfaced here.
BASE_COMMITTED = dict(digest="d7ad8f6296049611", rows=13541,
                      superseded=dict(digest="5d3469549fead8ac", rows=13525,
                                      recorded_at="5d7c084 (2026-11-20 16:30)",
                                      reproduces_at_origin=False),
                      rederived_at="origin/main 7dcc262, clean worktree, 2026-11-21",
                      attribution="f1d32c7, ROBOT_DEADLINE_S 5.0 -> 3.0 (D154 (1)); established by bisect plus a trace field diff showing exactly 20 rows differing in deadline_s alone. 34a4af0 and 2b8714c are both innocent.",
                      representations={"D2": 372},
                      source="results/orchestration/live2/frozen_test/value_reader_proofs.json")
# The frames-store cell for the cached-token proof. Small on purpose: the proof is a property of
# the wire form of one session's recall, so the cell only has to contain whole robot sessions that
# are warmed and then questioned.
# It runs on EP-G, because that is the workload the H100's cells run (D153) and because the EP-G
# charge is the episode's NEW tokens, so the dashcam traffic competes for the accelerator budget
# the way it will in the live cell. `test_hybrid.dry` has no `dashcam_format` parameter and is not
# a file this session owns, so `proofs()` above runs on dashcam-1f traces; the warm-ahead channel
# is a robot-side channel and the dashcam format does not touch it, but the difference is stated
# rather than assumed and both arms of each comparison are on the same format.
TOKCELL = dict(seed=4, n=8, run_s=600.0, ratio="50:50",
               robot_question_set="lh_req", ss_question_set="ss2",
               dashcam_format="epg")


def _digest(rows, ignore=()):
    import hashlib
    import json
    rr = [{k: v for k, v in r.items() if k not in ignore} for r in rows]
    return hashlib.sha256(json.dumps(rr, sort_keys=True, separators=(",", ":"),
                                     default=float).encode()).hexdigest()[:16]


def _dry(arm_name, cell=None):
    import test_hybrid as TH
    c = dict(CELL if cell is None else cell)
    rows, st = TH.dry(arm_name, c["seed"], c["n"], run_s=c["run_s"], ratio=c["ratio"],
                      robot_question_set=c["robot_question_set"],
                      ss_question_set=c["ss_question_set"])
    return rows, dict(st or {})


def _pieces(rows):
    """The characteristic DECISION, as an OBSERVED COUNT off the coordinator's own decision log:
    one row per prefill piece the coordinator issued. Not the arm's ask count."""
    return sum(1 for r in rows if str(r.get("kind")) in ("release_piece", "release_whole"))


def cached_token_proof(cell=None) -> Dict[str, Any]:
    """PROOF 2: at question time, a warmed history's recall request reuses a prompt prefix the
    engine has already been sent, where the base's does not.

    WHAT IS MEASURED, AND IN WHICH REGISTER. No GPU and no engine, so vLLM's own `cached_tokens`
    is NOT measured here and is not claimed: `backend.cached_tokens_of` needs a usage block. What
    is measured is the only thing that drives cached tokens, which is how much of the recall's
    prompt the engine has already been sent. `coordinator._submit_recall` sends the first
    `len(s.sent_bytes_for)` frames of the history as uuid-only REFERENCES and the rest as bytes,
    and `sent_bytes_for` advances only for a frame whose bytes actually went out
    (`coordinator.py:771`). This is the same register as `reports/study_epg_bodies.md` proof (a),
    which labelled it the same way; the engine-side confirmation is the H100's run.

    THE TRAP THIS PROOF IS BUILT AROUND. Without a resolved frame store `coordinator._path`
    returns None, every frame goes as a uuid-only reference, and the proof shows a PERFECT reuse
    with ZERO frames ever carrying bytes, which proves nothing. So a placeholder store is built
    for every frame_ref the trace asks for, `preflight.check` confirms the refs resolve, and
    `n_unresolved` is carried and reported. The base and the treatment are run against the SAME
    store on the SAME trace; a cell without a store is never compared against one with it.
    """
    import json
    import tempfile
    import arms as A
    import cachekeys as CK
    import cstate as CS
    import fleet.data_sources as DS
    import fleet.emulator as EM
    import fleet.trace as TR
    import preflight as PF
    from bridge import EmulatorBridge
    from coordinator import Live2Coordinator, Logs
    # The committed capacity constants, taken from the same module `epg_bodies_proof.py` takes
    # them from rather than retyped. Added to the path here and not at module import, because the
    # arm itself must not need live2's test directory to be importable.
    if str(HERE / "tests") not in sys.path:
        sys.path.insert(0, str(HERE / "tests"))
    from test_live2_coord import GPU_KV, HOST_GIB, HOST_TOK
    import hybrid                                                        # noqa: F401
    register()
    c = dict(TOKCELL if cell is None else cell)

    def one(arm_name, td, froot):
        a = A.make_arm(arm_name)
        a.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                          host_tier_tokens=HOST_TOK, targets=CS.TARGETS)
        with tempfile.TemporaryDirectory() as d:
            logs = Logs(Path(d) / "r").open()
            co = Live2Coordinator(a, None, [], gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                                  host_tier_tokens=HOST_TOK, upload_mode="A",
                                  window_s=c["run_s"], drain_s=5.0, seed=c["seed"], logs=logs,
                                  frames_root=froot, run_tag=CK.run_tag(c["seed"], "v5rules"),
                                  dry_run=True)
            recalls: List[Dict[str, Any]] = []
            orig = co._submit

            def spy(**kw):
                rid = orig(**kw)
                sub = co.futures[-1][1]
                if sub.kind == "recall":
                    parts = sub.body["messages"][0]["content"]
                    carries = ["bytes" if p.get("image_url") else "reference"
                               for p in parts if p.get("type") == "image_url"]
                    recalls.append(dict(
                        request_id=rid, session_id=sub.session_id, device_id=sub.device_id,
                        t=round(sub.sent_s, 6), est_tokens=int(sub.est_tokens),
                        n_frames=len(carries), n_reference=carries.count("reference"),
                        n_bytes=carries.count("bytes")))
                return rid
            co._submit = spy
            br = EmulatorBridge(co)
            br.kind = "stub"
            EM.FleetEmulator(td, br, "A", realtime=False, drain_s=5.0).run(Path(d) / "r")
            logs.close()
            res = co._result(0.0, 1.0)
            # Confirm the format the coordinator actually read OFF THE WIRE rather than assume
            # the one the trace was asked for: a proof labelled EP-G that ran one-frame would be
            # a label in the wrong register.
            fmt = dict(dashcam_format=res.get("dashcam_format"),
                       epg_counts={k: int(v) for k, v in (res.get("counts") or {}).items()
                                   if str(k).startswith("epg")},
                       budget_refusals=int((res.get("counts") or {}).get("budget_refusal", 0)))
            rows = [json.loads(ln) for ln in open(Path(d) / "r" / "decision.jsonl")]
        return recalls, rows, dict(getattr(a, "stats", None) or {}), fmt

    # D147's robot deadline, 3 s. The trace generator takes no deadline argument and reads
    # `DS.ROBOT_DEADLINE_S` at call time, so it is set here exactly as `frozen_headline.py:68-76`
    # does, and restored after. The committed default is still 5.0 (`data_sources.py:43`), which
    # is why `proofs()` runs at 5 s: its positive control is a committed digest measured at the
    # default, and changing the deadline there would invalidate the control rather than the arm.
    # 3 s is the regime D147 says warming is for, so this proof is run in it.
    prev_deadline = DS.ROBOT_DEADLINE_S
    DS.ROBOT_DEADLINE_S = float(c.get("robot_deadline_s", 3.0))
    # D154 (4)'s robot upload contract, passed ONLY if the committed generator takes it. The arm
    # needs no change to pick per-frame upload up, because a per-frame upload is a `history_batch`
    # with one frame and the record kind is unchanged; this keeps the proof runnable on a tree
    # where the switch does not exist yet, instead of hard-failing on its absence.
    import inspect
    gen_kw = {}
    if "robot_upload" in inspect.signature(TR.generate_trace).parameters:
        gen_kw["robot_upload"] = c.get("robot_upload", "batch-30s")
    elif c.get("robot_upload", "batch-30s") != "batch-30s":
        raise RuntimeError("robot_upload=%r asked for, but this tree's trace generator has no "
                           "such parameter" % (c.get("robot_upload"),))
    try:
        with tempfile.TemporaryDirectory() as d:
            td, froot = Path(d) / "t", Path(d) / "frames"
            TR.write_trace(td, TR.generate_trace(c["seed"], c["n"], c["ratio"], c["run_s"], "A",
                                                 robot_question_set=c["robot_question_set"],
                                                 ss_question_set=c["ss_question_set"],
                                                 dashcam_format=c["dashcam_format"], **gen_kw))
            refs = PF.trace_frame_refs(td)
            froot.mkdir(parents=True, exist_ok=True)
            for i, ref in enumerate(refs):
                q = froot / ref
                q.parent.mkdir(parents=True, exist_ok=True)
                q.write_bytes(b"\xff\xd8\xff" + bytes([i % 251]) * 64)
            pre = PF.check(td, froot)
            n_unresolved = len(pre.get("missing") or []) + len(pre.get("empty") or [])
            base_rc, base_rows, _base_st, base_fmt = one(V5RULES_BASE, td, froot)
            v5_rc, v5_rows, v5_st, v5_fmt = one("v5-rules", td, froot)
    finally:
        DS.ROBOT_DEADLINE_S = prev_deadline

    def summ(rc):
        reuse = [r for r in rc if r["n_reference"] > 0]
        # 338 tokens per image is `bodies.epg_prompt_tokens`' own per-frame constant. The reused
        # prefix is reported in FRAMES, which is what is observed; the token figure is DERIVED and
        # is a LOWER bound, because the engine rounds reuse to block boundaries.
        return dict(recalls=len(rc), recalls_reusing_a_prefix=len(reuse),
                    frames_total=sum(r["n_frames"] for r in rc),
                    frames_as_reference=sum(r["n_reference"] for r in rc),
                    frames_as_bytes=sum(r["n_bytes"] for r in rc),
                    reused_prefix_tokens_lower_bound=sum(r["n_reference"] for r in rc) * 338,
                    per_recall=[dict(session_id=r["session_id"], t=r["t"],
                                     n_frames=r["n_frames"], n_reference=r["n_reference"],
                                     n_bytes=r["n_bytes"], est_tokens=r["est_tokens"])
                                for r in rc])

    b, v = summ(base_rc), summ(v5_rc)
    # CLAUDE.md check 3 and the register rule: the two arms do NOT release the same recalls, so a
    # total-against-total comparison of frames would mix TWO effects, prefix reuse and a changed
    # set of admitted questions, in one column. They are separated here: the reuse claim is made
    # on the recalls BOTH arms released, and the count difference is reported as its own quantity.
    bk = {(r["session_id"], r["t"]): r for r in base_rc}
    vk = {(r["session_id"], r["t"]): r for r in v5_rc}
    shared = sorted(set(bk) & set(vk))
    paired = [dict(session_id=k[0], t=k[1], n_frames=vk[k]["n_frames"],
                   base_n_reference=bk[k]["n_reference"], v5_n_reference=vk[k]["n_reference"],
                   base_n_bytes=bk[k]["n_bytes"], v5_n_bytes=vk[k]["n_bytes"])
              for k in shared]
    paired_block = dict(
        shared_recalls=len(shared),
        every_shared_recall_reuses_more=bool(paired and all(
            p["v5_n_reference"] > p["base_n_reference"] for p in paired)),
        base_frames_as_reference=sum(p["base_n_reference"] for p in paired),
        v5_frames_as_reference=sum(p["v5_n_reference"] for p in paired),
        base_frames_as_bytes=sum(p["base_n_bytes"] for p in paired),
        v5_frames_as_bytes=sum(p["v5_n_bytes"] for p in paired),
        per_recall=paired)
    admission = dict(
        recalls_base=len(base_rc), recalls_v5_rules=len(v5_rc),
        only_in_v5_rules=[dict(session_id=k[0], t=k[1], n_frames=vk[k]["n_frames"],
                               est_tokens=vk[k]["est_tokens"]) for k in sorted(set(vk) - set(bk))],
        only_in_base=[dict(session_id=k[0], t=k[1]) for k in sorted(set(bk) - set(vk))],
        declines_base=sum(1 for r in base_rows if str(r.get("kind")) == "decline"),
        declines_v5_rules=sum(1 for r in v5_rows if str(r.get("kind")) == "decline"),
        note=("a recall the base declines and v5-rules releases is the causal chain's last link, "
              "not a confound: the base's feasibility test refuses a history it would have to "
              "rebuild cold inside the deadline, and the same history already warm is feasible. "
              "It is reported as its own quantity and is NOT folded into the reuse column."))
    out = dict(
        robot_upload=dict(asked=c.get("robot_upload", "batch-30s"),
                          passed_to_generator=("robot_upload" in gen_kw),
                          supported_by_this_tree=("robot_upload" in gen_kw)),
        paired_on_shared_recalls=paired_block,
        admission=admission,
        cell=dict(c, dry=True, robot_deadline_s=float(c.get("robot_deadline_s", 3.0)),
                  frames_root="placeholder store, one file per trace frame_ref"),
        frames_store=dict(refs=len(refs), n_unresolved=n_unresolved,
                          preflight_ok=bool(n_unresolved == 0),
                          note=("the bytes are not JPEGs and nothing is scored from them; the "
                                "proof is of the WIRE FORM. Without this store every frame goes "
                                "as a uuid reference and the proof measures nothing.")),
        dashcam_format_as_read_off_the_wire=dict(base=base_fmt, v5_rules=v5_fmt),
        register=("a WIRE-FORM measurement, not an engine measurement and not a belief. vLLM's "
                  "own cached_tokens needs a usage block and is the H100's to report. The reused "
                  "prefix is an OBSERVED COUNT of frames sent as uuid references; the token "
                  "figure is DERIVED at 338 tokens per image and is a LOWER bound."),
        base=dict(arm=V5RULES_BASE, prefills_issued=_pieces(base_rows), **b),
        v5_rules=dict(arm="v5-rules", prefills_issued=_pieces(v5_rows), **v),
        arm_asks=dict(emitted=int(v5_st.get("warm_ahead_emitted", 0)),
                      wanted=int(v5_st.get("warm_ahead_wanted", 0)),
                      unexpressible=int(v5_st.get("warm_ahead_unexpressible", 0)),
                      yielded_epochs=int(v5_st.get("warm_ahead_yielded_epochs", 0)),
                      _register="ASKS, one per candidate session per epoch; not a decision count"))
    # The verdict is taken on the PAIRED comparison, not on the totals, for the reason above.
    rose = (paired_block["every_shared_recall_reuses_more"]
            and paired_block["v5_frames_as_bytes"] < paired_block["base_frames_as_bytes"]
            and n_unresolved == 0)
    out["verdict"] = (
        "PASS on the %d recalls BOTH arms released: the prefix the engine has already been sent "
        "rises from %d frames to %d, so the bytes the question itself must carry fall from %d to "
        "%d, on every one of them, with 0 unresolved frames. Separately and reported as its own "
        "quantity, v5-rules released %d recalls against the base's %d."
        % (paired_block["shared_recalls"], paired_block["base_frames_as_reference"],
           paired_block["v5_frames_as_reference"], paired_block["base_frames_as_bytes"],
           paired_block["v5_frames_as_bytes"], len(v5_rc), len(base_rc)) if rose else
        "FAIL or UNEXERCISED: reference frames base %d, v5-rules %d, frames carrying bytes base "
        "%d, v5-rules %d, unresolved %d"
        % (b["frames_as_reference"], v["frames_as_reference"], b["frames_as_bytes"],
           v["frames_as_bytes"], n_unresolved))
    return out



def perframe_pickup() -> Dict[str, Any]:
    """D154 (4): `v5-rules` picks up per-frame robot upload with NO change to the arm, and this
    measures it instead of asserting it.

    Why no change is needed: a per-frame upload is a `history_batch` carrying one frame, the
    record kind is unchanged, and the warm-ahead rule asks for every candidate robot session every
    epoch, so a finer upload grain simply gives `_advance_build` newly uploaded frames on more
    epochs. The committed per-frame proof measured the same effect on `warm-all-lru` (180 to 588
    prefill pieces, 3.27x, on an 8-device 300 s cell) and named `v5-rules` as the arm it bears on.

    Both conditions are run with the SAME store, deadline, format, seed and cell, and the only
    difference is the contract. The two are never mixed in one number: every `v5-rules` cell is
    labelled with the contract it ran under.
    """
    import inspect
    import fleet.trace as TR
    if "robot_upload" not in inspect.signature(TR.generate_trace).parameters:
        return dict(supported=False,
                    note=("this tree's trace generator has no robot_upload parameter, so the "
                          "switch has not landed; v5-rules runs under batch-30s and needs no "
                          "change to pick the switch up when it does"))
    a = cached_token_proof(dict(TOKCELL, robot_upload="batch-30s"))
    b = cached_token_proof(dict(TOKCELL, robot_upload="per-frame"))

    def pick(x):
        return dict(prefills_issued=x["v5_rules"]["prefills_issued"],
                    prefills_issued_base=x["base"]["prefills_issued"],
                    recalls=x["v5_rules"]["recalls"], recalls_base=x["base"]["recalls"],
                    shared_recalls=x["paired_on_shared_recalls"]["shared_recalls"],
                    v5_frames_as_reference=x["paired_on_shared_recalls"]["v5_frames_as_reference"],
                    v5_frames_as_bytes=x["paired_on_shared_recalls"]["v5_frames_as_bytes"],
                    base_frames_as_reference=(
                        x["paired_on_shared_recalls"]["base_frames_as_reference"]),
                    base_frames_as_bytes=x["paired_on_shared_recalls"]["base_frames_as_bytes"],
                    asks=x["arm_asks"], verdict=x["verdict"])
    out = dict(supported=True, cell=dict(TOKCELL, robot_deadline_s=3.0, dry=True),
               batch_30s=pick(a), per_frame=pick(b))
    n_a = a["v5_rules"]["prefills_issued"]
    n_b = b["v5_rules"]["prefills_issued"]
    out["ratio_per_frame_over_batch"] = (round(n_b / n_a, 3) if n_a else None)
    out["verdict"] = (
        "PICKED UP with no change to the arm: %d prefills issued under per-frame against %d under "
        "batch-30s, the base issuing %d under both. The arm file contains no reference to the "
        "contract beyond passing it to the trace generator."
        % (n_b, n_a, b["base"]["prefills_issued"]) if n_b > n_a else
        "NOT PICKED UP or UNEXERCISED: per-frame %d, batch-30s %d" % (n_b, n_a))
    return out


def proofs(cell=None) -> Dict[str, Any]:
    """The three proofs the user named, plus Step 2b and the Step 4 negative control.

    Order matters: CLAUDE.md check 7 first, because a broken control passes every check applied to
    the treatment, and nothing below may be read if the base does not reproduce its committed
    digest in this harness.
    """
    import baseline_prescreen as BP
    import test_hybrid as TH
    import hybrid                                                        # noqa: F401
    register()
    c = dict(CELL if cell is None else cell)
    IGNORE = ("arm_version",)        # the coordinator writes the arm's label into every row

    out: Dict[str, Any] = dict(version=V5RULES_VERSION, arm="v5-rules", base=V5RULES_BASE,
                               engine_actions_version=EA.ENGINE_ACTIONS_VERSION,
                               cell=dict(c, dry=True))

    base, base_st = _dry(V5RULES_BASE, c)
    off, off_st = _dry("v5-rules-off", c)
    v5, v5_st = _dry("v5-rules", c)

    from collections import Counter as _C
    reps = {k: int(n) for k, n in _C(r.get("representation") for r in base
                                     if r.get("kind") == "release_recall").items()
            if k is not None}
    bc = BP.census(base)
    out["check7_positive_control"] = dict(
        quantity="hybrid-F-lhreq-noc3 decision digest, rows and representations at this cell",
        this_digest=_digest(base), prior_digest=BASE_COMMITTED["digest"],
        this_rows=len(base), prior_rows=BASE_COMMITTED["rows"],
        this_representations=reps, prior_representations=BASE_COMMITTED["representations"],
        source_of_prior=BASE_COMMITTED["source"],
        base_feasibility_actions=int(bc["feasibility_actions"]),
        agree=bool(_digest(base) == BASE_COMMITTED["digest"]
                   and len(base) == BASE_COMMITTED["rows"]
                   and reps == BASE_COMMITTED["representations"]),
        note=("the digest is computed over the decision rows INCLUDING arm_version, which is the "
              "register the committed value is in: every hybrid arm reports live2-arm-1.0, which "
              "is why the committed digests of five differently named hybrids coincide. A FAILURE "
              "here means the check is broken, not the arm, and nothing below may be read."))

    # PROOF 3 first of the three, because it is the cheapest and gates the rest: an illegal action
    # raises inside `Policy.__call__`, so a cell that completes with a non-empty log emitted none.
    out["proof_illegal_actions"] = dict(
        illegal_actions=0, decisions=len(v5), completed=True,
        base_decisions=len(base), off_decisions=len(off),
        note=("validate_action runs on every epoch inside Policy.__call__ and raises on anything "
              "outside the registered domain, including a MATERIALIZE naming a session the "
              "observation did not contain; a completed cell emitted no such action"))

    # PROOF 1: the characteristic decision. ISSUED, off the decision log, with the ASKS beside it.
    n_v5, n_base, n_off = _pieces(v5), _pieces(base), _pieces(off)
    out["proof_warm_ahead_prefills"] = dict(
        prefills_issued=n_v5, prefills_issued_base=n_base, prefills_issued_off=n_off,
        _register=("prefills_issued is an OBSERVED COUNT of release_piece / release_whole rows in "
                   "the coordinator's own decision log. warm_ahead_* below are the arm's ASKS, "
                   "one per candidate robot session per epoch, most of which no-op inside "
                   "_advance_build; they are not a decision count and are never summed with it."),
        characteristic=("warm_ahead_prefill: a MATERIALIZE for a robot session with no pending "
                        "question, issued ahead of its question"),
        arm_asks=dict(emitted=int(v5_st.get("warm_ahead_emitted", 0)),
                      wanted=int(v5_st.get("warm_ahead_wanted", 0)),
                      unexpressible=int(v5_st.get("warm_ahead_unexpressible", 0)),
                      yielded_epochs=int(v5_st.get("warm_ahead_yielded_epochs", 0))),
        release_readiness_belief={k: int(v) for k, v in sorted(v5_st.items())
                                  if k.startswith("release_at_")},
        # The comparator is `v5-rules-off`, NOT the base arm. The base is a plain HybridArm and
        # does not carry this counter at all, so its slot would be an EMPTY DICT, which a reader
        # would take for "the base released nothing warm" when it means "the base was not
        # counted". `v5-rules-off` is byte-identical to the base and does carry the counter.
        release_readiness_belief_off=({k: int(v) for k, v in sorted(off_st.items())
                                       if k.startswith("release_at_")}
                                      or "none counted"),
        release_readiness_belief_base_not_instrumented=(
            not any(k.startswith("release_at_") for k in base_st)),
        _readiness_register=("this is the arm's BELIEF at release time. On a PARTIALLY built "
                             "history the belief stays COLD while the built prefix is already "
                             "reused on the wire as uuid references (coordinator.py:745-752, "
                             "spec v5 section 8), so a COLD release here is NOT evidence that "
                             "the request was uncached. The wire-form measurement is "
                             "cached_token_proof()."))
    out["proof_warm_ahead_prefills"]["verdict"] = (
        "PASS: %d prefills issued where the base issues %d" % (n_v5, n_base) if n_v5 > n_base else
        ("FAIL: 0 prefills issued. asked %d, unexpressible %d. If unexpressible is non-zero the "
         "arm self-censored at engine_actions.known_sessions, which reads obs.live_sessions: "
         "check PATCH 1 is on the harness under test (interface.Observation.live_sessions, "
         "validate_action's known_sessions, cstate.observation). This is Rule 2 UNEXPRESSIBLE and "
         "NOT a negative."
         % (int(v5_st.get("warm_ahead_wanted", 0)),
            int(v5_st.get("warm_ahead_unexpressible", 0)))))

    # STEP 4, the negative control: the mechanism disabled must collapse to the base byte-identically.
    out["step4_negative_control"] = dict(
        control_arm="v5-rules-off", mechanism_disabled="warm_ahead",
        base_digest=_digest(base, IGNORE), control_digest=_digest(off, IGNORE),
        treatment_digest=_digest(v5, IGNORE),
        control_identical_to_base=bool(_digest(off, IGNORE) == _digest(base, IGNORE)),
        control_identical_including_arm_version=bool(off == base),
        prefills_issued_off=n_off,
        _register=("identity is asserted on the decision rows with arm_version REMOVED, because "
                   "the coordinator writes that label into every row and a new arm necessarily "
                   "carries a new one; the unstripped comparison is reported beside it so the "
                   "label difference is visible rather than hidden."),
        note=("the control must collapse to the base BYTE-IDENTICALLY, which is stronger than "
              "'converges'. A treatment digest equal to the base's would instead be an ABSENT "
              "LINK."))
    out["step4_negative_control"]["verdict"] = (
        "PASS: disabling warm_ahead reproduces the base exactly and issues %d prefills" % n_off
        if (_digest(off, IGNORE) == _digest(base, IGNORE) and n_off == n_base) else
        "FAIL: the control does not collapse to the base, so what v5-rules measures is not the "
        "warming channel")

    # STEP 2b: does the switch reach a DECISION? Setwise, because a reordering is not a decision.
    first = next((i for i, (x, y) in enumerate(zip(base, v5)) if x != y), None)
    out["step2b_decision_diff"] = dict(
        vs=V5RULES_BASE,
        differing_setwise=TH._differing_setwise(base, v5),
        differing_positional=TH._differing(base, v5),
        first_differing_index=first,
        first_differing_row_v5_rules=(v5[first] if first is not None else None),
        first_differing_row_base=(base[first] if first is not None and first < len(base)
                                  else None),
        _register=("the setwise count is the decision count; the positional count is reported "
                   "beside it because one early divergence desynchronises the rest of the log "
                   "(test_hybrid._differing's own docstring)."))
    out["step2b_decision_diff"]["verdict"] = (
        "PASS" if TH._differing_setwise(base, v5) > 0 else
        "ABSENT LINK: the two conditions decided identically, so the comparison has not been run")

    out["summary"] = dict(
        positive_control=out["check7_positive_control"]["agree"],
        proof_warm_ahead_prefills=bool(n_v5 > n_base),
        proof_illegal_actions=True,
        step4_negative_control=bool(_digest(off, IGNORE) == _digest(base, IGNORE)
                                    and n_off == n_base),
        step2b=bool(TH._differing_setwise(base, v5) > 0),
        cached_tokens="see cached_token_proof(); run separately because it needs a frames store")
    out["summary"]["all_pass"] = bool(all(v is True for k, v in out["summary"].items()
                                          if k != "cached_tokens"))
    return out


def main(argv=None) -> int:
    import json
    argv = list(sys.argv[1:] if argv is None else argv)
    which = argv[0] if argv else "all"
    out0 = REPO / "results/orchestration/live2/v5rules/v5_rules_proofs.json"
    # MERGE, do not overwrite: the two halves are run separately (the cached-token half needs a
    # frames store and its own trace) and a plain write of one half would silently delete the
    # other from the artefact.
    res: Dict[str, Any] = {}
    if out0.exists():
        try:
            res = json.loads(out0.read_text())
        except Exception:                                                      # noqa: BLE001
            res = {}
    res.pop("_provenance", None)
    if which in ("all", "proofs"):
        res["proofs"] = proofs()
    if which in ("all", "tokens"):
        res["cached_token_proof"] = cached_token_proof()
    out = REPO / "results/orchestration/live2/v5rules/v5_rules_proofs.json"
    try:
        import _provenance
        res["_provenance"] = _provenance.stamp(script="arms_v5rules.py", model="none-dry",
                                               device="nvidia_rtx_a6000", n=16)
    except Exception as e:                                                     # noqa: BLE001
        res["_provenance"] = {"git_commit": "unstamped", "script": "arms_v5rules.py",
                              "note": "stamp failed: %r" % (e,)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2, default=float))
    print(json.dumps({k: v for k, v in res.items() if k != "_provenance"}, indent=2,
                     default=float)[:12000])
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
