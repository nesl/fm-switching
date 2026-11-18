#!/usr/bin/env python3
"""The round-1 opportunity trace: what every emulated device would offer, second by second.

StudyLIVE2-fleet, part 3. CPU only. Nothing here runs a model, touches a GPU or opens a socket.
A trace produced by this module is NOT a measurement: it is a deterministic script, replayed
identically by every arm, which is what D69 and D79 mean by a paired comparison.

WHAT A TRACE IS, AND WHY IT IS MODE-INDEPENDENT

D69 defines fairness across arms as IDENTICAL OPPORTUNITY STREAMS: the same instants and the
same questions arrive at every arm, and under pull mode (B) each arm requests the frames it
would serve. The opportunity stream is therefore the invariant, not the wire traffic. So the
trace holds OPPORTUNITIES, and `emulator.py` turns each one into the wire event its mode
requires (mode A: `monitor_frame` pushed; mode B: `monitor_offer`, then `monitor_frame` after a
`pull_request`). `mode` is recorded in the trace metadata and does NOT change one byte of
trace.jsonl, so the same trace file serves both modes and the two modes are comparable by
construction. `tests/test_trace.py` asserts it.

RULINGS IMPLEMENTED HERE

  D67       ratio dashcam : robot in {50:50, 75:25, 25:75}; no device mixes datasets.
  D83       each robot device plays a SEEDED SEQUENCE of EVAL sessions back to back; a new
            session is a new task and its history starts from zero; `session_start` /
            `session_end` are emitted; the first session starts at a staggered seeded offset.
  D84/D85   distinct clips and sessions are assigned FIRST and repeat only when the pool is
            exhausted; every play gets its own play id; repeat counts are reported and repeats
            are not independent samples.
  D68       robot questions at their REAL annotated times; history uploaded in fixed batches
            every 30 s with StudyRH4's D2 token accounting; predictive upload off.
  D62/D71   one monitoring opportunity per decision instant on the committed 0.5-s cadence,
            L = 1.0 s; robot questions L = 5.0 s.
  D79       seeds fix assignment, start offsets and order IDENTICALLY for all arms.
  D96 (1)   every opportunity carries an `opportunity_id`, unique within the run and ASSIGNED
            HERE, not constructed by anyone downstream. It is a flat `opp<n>` label handed out
            in the trace's canonical order, so nothing can be parsed out of it and a repeated
            clip or session (D84) can never collide. The descriptive fields a scorer or a joiner
            needs - `play_id`, `clip`, `t_local`, `session_id`, `question_id` - travel alongside
            it in the trace, never inside it.
  D96 (2)   the canonical FAIRNESS DIGEST is `fairness_digest`: an order-independent sha256 over
            sorted event tuples covering device_register, session_start, session_end,
            history_append, recall_question, and monitor_offer in PULL mode or monitor_frame in
            PUSH mode. In pull mode frames are excluded, because which frames exist depends on
            the arm's pulls.

THE STAGGERED OFFSET, AND THE ONE READING THAT HAD TO BE CHOSEN

D83 says "the first session starts at a staggered seeded offset" and part 3 says dashcam clips
run "back to back at the CTRL1c cadence from a seeded offset". Both are implemented as an offset
in RUN TIME: a device registers at t = 0 and begins its first clip or session at
`start_t` ~ U[0, stagger_s), seeded. The alternative reading - starting part-way INTO the first
clip or session - was rejected for two reasons, both recorded in the report: D83 states that a
new session's history starts from zero, which a mid-session join contradicts, and D85 excludes
"plays cut by the run end", which presupposes whole plays. `stagger_s` defaults to the 30-s
history-batch period so batch boundaries and instant phases are decorrelated across devices
rather than fleet-synchronous; it is a parameter and is reported with its value.

FRAME BYTES

Part 2 (the JPEG encode, D91) does not run on flash, so no per-frame byte count exists yet. The
trace carries the COMMITTED E10a median per frame and records `frame_bytes_source`. Once a
Part-2 manifest exists, pass it as `frame_manifest` and the per-frame byte counts are read from
it instead; the header then says so. A median stands in for a distribution, which the report
lists as a limitation of any run made before Part 2.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import data_sources as DS

RATIOS = {"50:50": (50, 50), "75:25": (75, 25), "25:75": (25, 75)}
MODES = ("A", "B")

OPPORTUNITY_KINDS = ("monitor_opportunity", "recall_question")
TRACE_KINDS = ("device_register", "session_start", "session_end", "history_batch",
               "monitor_opportunity", "recall_question")

# D96 (2): what the canonical fairness digest covers, and the wire kind each trace record maps to.
# `monitor_opportunity` becomes `monitor_frame` in push mode and `monitor_offer` in pull mode;
# monitor_frame in PULL mode is deliberately absent, because the arm's pulls decide which frames
# exist at all.
DIGEST_KINDS = ("device_register", "session_start", "session_end", "history_batch",
                "recall_question", "monitor_opportunity")
MONITOR_WIRE_KIND = {"A": "monitor_frame", "B": "monitor_offer"}

DEFAULT_STAGGER_S = DS.HISTORY_BATCH_S      # 30 s, the D68 history-batch period
ANSWER_PAYLOAD_B = 300                      # a cloud answer body; see links.deliver_s


# ---------------------------------------------------------------- deterministic dealing
def _deal(pool: Sequence[str], want: Sequence[int], rng: random.Random) -> List[List[str]]:
    """Deal items to devices DISTINCT-FIRST, repeating only once the pool is exhausted (D84).

    `want[i]` is how many items device i needs. One shuffled pass over the pool is dealt
    round-robin, so no item is used twice until every item has been used once; further passes
    are fresh shuffles. Returns one list per device.
    """
    out: List[List[str]] = [[] for _ in want]
    order = list(pool)
    rng.shuffle(order)
    cursor = 0
    i = 0
    remaining = list(want)
    while any(r > 0 for r in remaining):
        if remaining[i] > 0:
            if cursor >= len(order):
                order = list(pool)
                rng.shuffle(order)
                cursor = 0
            out[i].append(order[cursor])
            cursor += 1
            remaining[i] -= 1
        i = (i + 1) % len(want)
    return out


def _split_fleet(n_devices: int, ratio: str) -> Tuple[int, int]:
    if ratio not in RATIOS:
        raise ValueError(f"ratio {ratio!r} not in {sorted(RATIOS)} (D67)")
    d, r = RATIOS[ratio]
    n_dash = int(round(n_devices * d / float(d + r)))
    return n_dash, n_devices - n_dash


# ---------------------------------------------------------------- the generator
@dataclass
class TraceStats:
    n_devices: int = 0
    n_dashcam: int = 0
    n_robot: int = 0
    dashcam_instants: Dict[str, int] = field(default_factory=dict)
    dashcam_meeting_200: int = 0
    dashcam_plays_started: int = 0
    dashcam_plays_completed: int = 0
    robot_questions_total: int = 0
    robot_questions_per_device: Dict[str, int] = field(default_factory=dict)
    robot_sessions_started: int = 0
    robot_sessions_completed: int = 0
    robot_history_batches: int = 0
    clip_play_counts: Dict[str, int] = field(default_factory=dict)
    session_play_counts: Dict[str, int] = field(default_factory=dict)
    clip_repeats: int = 0
    session_repeats: int = 0

    def as_dict(self) -> Dict[str, Any]:
        d = dict(self.__dict__)
        d["dashcam_min_instants"] = min(self.dashcam_instants.values()) if self.dashcam_instants \
            else None
        d["robot_pool_meets_20"] = self.robot_questions_total >= 20
        return d


def generate_trace(seed: int, n_devices: int, ratio: str, run_s: float, mode: str,
                   stagger_s: float = DEFAULT_STAGGER_S,
                   frame_manifest: Optional[Path] = None,
                   count_only: bool = False) -> Dict[str, Any]:
    """Build one run's opportunity trace. Returns {records, device_answers, meta, stats}.

    Deterministic in `seed` alone given (n_devices, ratio, run_s, stagger_s): the same seed
    produces a byte-identical trace, which is what makes the arms paired (D79).

    `count_only=True` runs the IDENTICAL control flow but skips building the wire records, the
    device-answer rows and the per-instant Orin lookups, returning `stats` with empty `records`
    and `device_answers`. It exists for the D97 eligibility table, which needs 1,500 cells and
    only ever reads `stats`. It is a SKIP, not a second implementation: every loop, bound,
    dealing step and stats update below is the same code in both modes, and
    `tests/test_live2_fleet.py` check (h) asserts the two agree exactly on a sample of cells.
    """
    if mode not in MODES:
        raise ValueError(f"mode {mode!r} not in {MODES} (D69)")
    if run_s <= 0:
        raise ValueError("run_s must be positive")
    n_dash, n_rob = _split_fleet(n_devices, ratio)

    clips = DS.nexar_clip_meta()
    sessions = DS.eval_sessions()
    orin = {} if count_only else DS.orin_dense_scores()
    dev_answers = {} if count_only else DS.device_recall_answers()

    frame_bytes_by_ref: Dict[str, int] = {}
    frame_bytes_source = "E10a committed median q90 (Part 2 not run)"
    default_frame_bytes = int(round(DS.E10A_NEXAR_Q90_MEDIAN_B))
    default_hist_frame_bytes = int(round(DS.E10A_SEMBER_Q88_D2_MEDIAN_B))
    if frame_manifest is not None:
        DS.require(Path(frame_manifest), "Part-2 JPEG manifest (D91)")
        for ln in open(frame_manifest):
            r = json.loads(ln)
            frame_bytes_by_ref[r["frame_ref"]] = int(r["bytes"])
        frame_bytes_source = f"Part-2 manifest {frame_manifest}"

    rng_clip = random.Random(f"{seed}|clips")
    rng_sess = random.Random(f"{seed}|sessions")
    rng_stag = random.Random(f"{seed}|stagger")

    dash_ids = [f"dash{i:03d}" for i in range(n_dash)]
    rob_ids = [f"robo{i:03d}" for i in range(n_rob)]

    mean_clip_s = (sum(c.duration_s for c in clips.values()) / len(clips)) if clips else 1.0
    mean_sess_s = (sum(s.duration_s for s in sessions.values()) / len(sessions)) if sessions \
        else 1.0
    # One spare item per device so a run never runs out mid-play.
    want_clips = [int(run_s / mean_clip_s) + 3] * n_dash
    want_sess = [int(run_s / mean_sess_s) + 3] * n_rob
    clip_plan = _deal(sorted(clips), want_clips, rng_clip) if n_dash else []
    sess_plan = _deal(sorted(sessions), want_sess, rng_sess) if n_rob else []

    records: List[Dict[str, Any]] = []
    answers: List[Dict[str, Any]] = []
    st = TraceStats(n_devices=n_devices, n_dashcam=n_dash, n_robot=n_rob)

    # start_t is drawn in a FIXED device order so the draw does not depend on the ratio split.
    start_t = {did: rng_stag.uniform(0.0, stagger_s) for did in dash_ids + rob_ids}

    for did in dash_ids:
        if not count_only:
            records.append(dict(kind="device_register", device_id=did, type="dashcam",
                                uplink_mbps=None, rtt_ms=None,
                                start_t=round(start_t[did], 6)))
        t = start_t[did]
        n_inst = 0
        for k, clip in enumerate(clip_plan[dash_ids.index(did)]):
            if t >= run_s:
                break
            cm = clips[clip]
            play_id = f"{did}|p{k:03d}|{clip}"
            completed = (t + cm.duration_s) <= run_s + 1e-9
            st.dashcam_plays_started += 1
            st.dashcam_plays_completed += int(completed)
            st.clip_play_counts[clip] = st.clip_play_counts.get(clip, 0) + 1
            for t_local in DS.nexar_instants(cm.duration_s):
                t_run = t + t_local
                if t_run > run_s + 1e-9:
                    break
                if not count_only:
                    key = (clip, round(t_local, 6))
                    if key not in orin:
                        raise DS.MissingInput(
                            f"no committed Orin device score for instant {key}; the dense "
                            f"StudyORIN1 set does not cover this clip at this cadence")
                    o = orin[key]
                    frame_ref = f"{clip}|t{t_local:07.2f}"
                    nb = frame_bytes_by_ref.get(frame_ref, default_frame_bytes)
                    opp = f"{play_id}|t{t_local:07.2f}"
                    records.append(dict(kind="monitor_opportunity", device_id=did,
                                        opportunity_key=opp, instant_id=opp, play_id=play_id,
                                        clip=clip, t=round(t_run, 6),
                                        t_local=round(t_local, 6),
                                        deadline_s=DS.NEXAR_DEADLINE_S, frame_ref=frame_ref,
                                        frame_bytes=nb, play_completed=completed))
                    answers.append(dict(opportunity_key=opp, device_id=did, kind="monitor",
                                        play_id=play_id, clip=clip,
                                        t_local=round(t_local, 6),
                                        device_score=o["score"], device_p_yes=o["p_yes"],
                                        device_latency_s=o["ttft_s"],
                                        device_total_s=o["total_s"]))
                n_inst += 1
            t += cm.duration_s
        st.dashcam_instants[did] = n_inst
    st.dashcam_meeting_200 = sum(1 for v in st.dashcam_instants.values() if v >= 200)
    st.clip_repeats = sum(v - 1 for v in st.clip_play_counts.values() if v > 1)

    for did in rob_ids:
        if not count_only:
            records.append(dict(kind="device_register", device_id=did, type="robot",
                                uplink_mbps=None, rtt_ms=None,
                                start_t=round(start_t[did], 6)))
        t = start_t[did]
        nq = 0
        for k, sid in enumerate(sess_plan[rob_ids.index(did)]):
            if t >= run_s:
                break
            sm = sessions[sid]
            play_id = f"{did}|s{k:03d}|{sid}"
            st.robot_sessions_started += 1
            st.session_play_counts[sid] = st.session_play_counts.get(sid, 0) + 1
            if not count_only:
                records.append(dict(kind="session_start", device_id=did, session_id=play_id,
                                    t=round(t, 6), source_session=sid,
                                    duration_s=round(sm.duration_s, 6)))
            # D83: a new session is a new task, so history restarts from zero here.
            b = 0
            emitted = 0
            tokens_sent = 0
            while True:
                b += 1
                w_from = (b - 1) * DS.HISTORY_BATCH_S
                w_to = min(b * DS.HISTORY_BATCH_S, sm.duration_s)
                if w_from >= sm.duration_s - 1e-9:
                    break
                fr = DS.d2_frames_in(w_from, w_to)
                t_offer = t + w_to
                if t_offer > run_s + 1e-9:
                    break
                if not fr:
                    # A trailing window shorter than the 2-s D2 stride holds no frame, so there
                    # is no history to upload and no batch is sent.
                    if w_to >= sm.duration_s - 1e-9:
                        break
                    continue
                tok = DS.d2_batch_tokens(len(fr), first_batch=(emitted == 0))
                emitted += 1
                tokens_sent += tok
                if not count_only:
                    records.append(dict(kind="history_batch", device_id=did,
                                        session_id=play_id,
                                        batch_id=f"{play_id}|b{b:03d}", t=round(t_offer, 6),
                                        frame_refs=[f"{sid}|f{x:08.2f}" for x in fr],
                                        est_tokens=tok, cum_tokens=tokens_sent,
                                        frame_bytes=len(fr) * default_hist_frame_bytes))
                st.robot_history_batches += 1
                if w_to >= sm.duration_s - 1e-9:
                    break
            for q in sm.questions:
                if q.t_ask > sm.duration_s + 1e-9:
                    continue
                t_run = t + q.t_ask
                if t_run > run_s + 1e-9:
                    continue
                if not count_only:
                    if q.question_id not in dev_answers:
                        raise DS.MissingInput(
                            f"no D87 device answer for EVAL question {q.question_id}")
                    da = dev_answers[q.question_id]
                    # The history the CLOUD holds now, by D2 accounting (StudyRH4).
                    nfr = len(DS.d2_frames_in(0.0, min(q.t_ask, sm.duration_s)))
                    hist_tok = DS.d2_batch_tokens(nfr, first_batch=True)
                    opp = f"{play_id}|{q.question_id}"
                    records.append(dict(kind="recall_question", device_id=did,
                                        session_id=play_id,
                                        opportunity_key=opp, question_id=q.question_id,
                                        t=round(t_run, 6), t_ask_session=round(q.t_ask, 6),
                                        deadline_s=DS.ROBOT_DEADLINE_S, question=q.question,
                                        options=q.options, gold_letter=q.gold_letter,
                                        category=q.category, history_tokens=hist_tok))
                    answers.append(dict(opportunity_key=opp, device_id=did, kind="recall",
                                        session_id=play_id, question_id=q.question_id,
                                        device_answer=da["pred"],
                                        device_correct=da["correct"], gold_letter=da["gold"],
                                        device_latency_s=DS.device_recall_latency_s(hist_tok),
                                        history_tokens=hist_tok))
                nq += 1
            t_end = t + sm.duration_s
            if t_end <= run_s + 1e-9:
                if not count_only:
                    records.append(dict(kind="session_end", device_id=did,
                                        session_id=play_id, t=round(t_end, 6)))
                st.robot_sessions_completed += 1
            t = t_end
        st.robot_questions_per_device[did] = nq
    st.robot_questions_total = sum(st.robot_questions_per_device.values())
    st.session_repeats = sum(v - 1 for v in st.session_play_counts.values() if v > 1)

    records.sort(key=lambda r: (round(float(r.get("t", 0.0)), 6),
                                TRACE_KINDS.index(r["kind"]), r["device_id"],
                                r.get("opportunity_key") or r.get("session_id") or ""))

    # D96 (1): the generator ASSIGNS every opportunity_id, in the trace's canonical order, so the
    # id is deterministic in the seed and carries no parsable structure. `opportunity_key` is
    # dropped from the wire records: nothing downstream may depend on it.
    assigned: Dict[str, str] = {}
    for r in records:
        if r["kind"] in OPPORTUNITY_KINDS:
            key = r.pop("opportunity_key")
            opp = f"opp{len(assigned):07d}"
            assigned[key] = opp
            r["opportunity_id"] = opp
            if r["kind"] == "monitor_opportunity":
                r["instant_id"] = opp
    for a in answers:
        a["opportunity_id"] = assigned[a.pop("opportunity_key")]
    answers.sort(key=lambda r: (r["device_id"], r["opportunity_id"]))

    meta = dict(seed=seed, n_devices=n_devices, ratio=ratio, run_s=run_s, mode=mode,
                stagger_s=stagger_s, n_dashcam=n_dash, n_robot=n_rob,
                cadence_s=DS.NEXAR_INSTANT_CADENCE_S,
                dashcam_deadline_s=DS.NEXAR_DEADLINE_S,
                robot_deadline_s=DS.ROBOT_DEADLINE_S,
                history_batch_s=DS.HISTORY_BATCH_S,
                frame_bytes_source=frame_bytes_source, count_only=count_only,
                answer_payload_bytes=ANSWER_PAYLOAD_B,
                trace_label="NOT A MEASUREMENT: a deterministic device script",
                mode_affects_trace=False,
                caveats=[DS.AP_CAVEAT, DS.DEVICE_ANSWER_CAVEAT, DS.SEMBER_JPEG_CAVEAT])
    return dict(records=records, device_answers=answers, meta=meta, stats=st.as_dict())


# ---------------------------------------------------------------- digests and io
def _canon(r: Dict[str, Any]) -> str:
    return json.dumps(r, sort_keys=True, separators=(",", ":"))


def _digest_tuple(r: Dict[str, Any], mode: str) -> Optional[Tuple[str, ...]]:
    """One canonical tuple per covered event (D96 (2)), or None if the event is not covered."""
    k = r["kind"]
    if k not in DIGEST_KINDS:
        return None
    dev = str(r["device_id"])
    if k == "device_register":
        return (dev, "device_register", f"{float(r['start_t']):.6f}", "", "", "")
    if k in ("session_start", "session_end"):
        return (dev, k, f"{float(r['t']):.6f}", str(r["session_id"]), "", "")
    if k == "history_batch":
        return (dev, "history_append", f"{float(r['t']):.6f}", str(r["batch_id"]),
                str(int(r["est_tokens"])), "")
    if k == "recall_question":
        return (dev, "recall_question", f"{float(r['t']):.6f}", str(r["opportunity_id"]),
                str(r["session_id"]), f"{float(r['deadline_s']):.6f}")
    # monitor_opportunity: the wire kind depends on the mode, and a PULLED frame is excluded.
    return (dev, MONITOR_WIRE_KIND[mode], f"{float(r['t']):.6f}", str(r["opportunity_id"]),
            "", f"{float(r['deadline_s']):.6f}")


def fairness_digest(records: Sequence[Dict[str, Any]], mode: str) -> str:
    """The canonical fairness digest (D96 (2)).

    An ORDER-INDEPENDENT sha256 over sorted event tuples, covering `device_register`,
    `session_start`, `session_end`, `history_append`, `recall_question`, and `monitor_offer` in
    PULL mode or `monitor_frame` in PUSH mode. Order-independent, so a tie-break in the
    emulator's heap cannot move it. Mode-dependent only in the monitor label: in pull mode the
    FRAMES are excluded, because which frames exist depends on the arm's pulls, and digesting
    them would make an arm that pulls less look like a different experiment.

    The trace FILE stays mode-independent; only this digest is taken per mode, and
    `write_trace` records both.
    """
    if mode not in MODES:
        raise ValueError(f"mode {mode!r} not in {MODES}")
    rows = [t for t in (_digest_tuple(r, mode) for r in records) if t is not None]
    h = hashlib.sha256()
    for row in sorted(rows):
        h.update(("|".join(row) + "\n").encode())
    return h.hexdigest()


def write_trace(out_dir: Path, bundle: Dict[str, Any]) -> Dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tp = out_dir / "trace.jsonl"
    ap = out_dir / "device_answers.jsonl"
    with open(tp, "w") as fh:
        for r in bundle["records"]:
            fh.write(_canon(r) + "\n")
    with open(ap, "w") as fh:
        for r in bundle["device_answers"]:
            fh.write(_canon(r) + "\n")
    meta = dict(bundle["meta"])
    meta["trace_sha256"] = DS.sha256_of(tp)
    meta["device_answers_sha256"] = DS.sha256_of(ap)
    meta["fairness_digest_A"] = fairness_digest(bundle["records"], "A")
    meta["fairness_digest_B"] = fairness_digest(bundle["records"], "B")
    meta["fairness_digest"] = meta[f"fairness_digest_{meta['mode']}"]
    meta["fairness_digest_definition"] = (
        "D96 (2) canonical: order-independent sha256 over sorted event tuples covering "
        "device_register, session_start, session_end, history_append, recall_question, and "
        "monitor_offer (pull mode) or monitor_frame (push mode). monitor_frame is EXCLUDED in "
        "pull mode because which frames exist depends on the arm's pulls.")
    meta["n_records"] = len(bundle["records"])
    meta["n_device_answers"] = len(bundle["device_answers"])
    meta["stats"] = bundle["stats"]
    (out_dir / "trace_meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    return meta


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--devices", type=int, required=True)
    ap.add_argument("--ratio", default="50:50", choices=sorted(RATIOS))
    ap.add_argument("--run-s", type=float, required=True)
    ap.add_argument("--mode", default="A", choices=list(MODES))
    ap.add_argument("--stagger-s", type=float, default=DEFAULT_STAGGER_S)
    ap.add_argument("--frame-manifest", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    b = generate_trace(a.seed, a.devices, a.ratio, a.run_s, a.mode, a.stagger_s,
                       Path(a.frame_manifest) if a.frame_manifest else None)
    meta = write_trace(Path(a.out), b)
    print(json.dumps(meta, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
