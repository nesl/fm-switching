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
            `session_end` are emitted.
  D101      ROBOT DEVICES JOIN THEIR FIRST SESSION PART-WAY. Each robot's first session is
            joined at a seeded point drawn uniformly in [0, 0.5 x session duration]; the draw is
            recorded per device in `trace_meta.json`. Questions before the join point are NOT
            emitted and NOT counted. At t = 0 the cloud already holds that session's earlier
            frames as cold history, declared by a `history_preload` event with D2 token
            accounting and NO uplink time charged. Batches after t = 0 continue on the same 30-s
            session-local grid, carrying only the frames the preload did not. LATER sessions in
            the chain start from zero (D83). D101 replaces CHOICE g of the analysis plan.
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
  D148/D153 THE DASHCAM EPISODE (`dashcam_format="epg"`; "oneframe" is the default and leaves
            every committed trace byte-identical). The dashcam format is fixed BY THE TASK:
            every dashcam query, device and cloud, carries the append-only episode context of
            D148, which is EP-G as StudySH-EP ran it, and never one frame per call. THE EPISODE
            FRAME LIST IS EMITTED HERE, deterministically and independently of any arm's
            release decisions, because D153 says each frame is prefilled AS CAPTURED: the
            episode accumulates every captured frame of the play whether or not an arm acted on
            that instant. That is what makes proof (b), an identical request digest across
            arms, hold BY CONSTRUCTION rather than by coordinator discipline. Each
            `monitor_opportunity` then carries `episode_id`, `episode_index` (the index within
            the refresh cycle), `frame_refs` (the ordered episode frames, oldest first) and
            `episode_frames` (their count). See EPG_REFRESH_NOTE for the refresh and the floor.
  D150/D154 THE ROBOT UPLOAD CONTRACT (`robot_upload="per-frame"`; "batch-30s" is the default
            and leaves every committed trace byte-identical). D154 (4) replaces D68's fixed
            30-s batches with ONE UPLOAD PER FRAME AS CAPTURED, for ALL arms. Like the episode
            frame list, the upload schedule is emitted HERE and is a function of the session's
            own D2 capture grid alone, so it cannot depend on any arm's decisions and the
            cross-arm upload digest is identical BY CONSTRUCTION. See ROBOT_UPLOAD_NOTE.
  D96 (2)   the canonical FAIRNESS DIGEST is `fairness_digest`: an order-independent sha256 over
            sorted event tuples covering device_register, session_start, session_end,
            history_append, recall_question, and monitor_offer in PULL mode or monitor_frame in
            PUSH mode. In pull mode frames are excluded, because which frames exist depends on
            the arm's pulls.

THE STAGGER, AS D101 SETTLED IT

An earlier build read D83's "staggered seeded offset" as an offset in RUN TIME for both device
classes, and recorded the alternative reading - starting part-way INTO the first clip or session
- as an open issue. D101 settled it, and the two classes now differ:

  DASHCAM   keeps the run-time stagger and the complete-play rule (D85). A dashcam device
            registers at t = 0 and begins its first clip at `start_t` ~ U[0, stagger_s), seeded,
            so `stagger_s` still decorrelates instant phases across devices. Plays are never
            joined part-way, which is what D85's "plays cut by the run end are excluded"
            presupposes.
  ROBOT     starts its first session AT t = 0 and joins it part-way, at `join_frac` ~ U[0, 0.5)
            of that session's duration, seeded (D101). The run-time offset is therefore NOT
            applied to a robot: D101 puts the preload at t = 0, which a device that has not yet
            registered cannot send, and the join draw decorrelates batch boundaries and question
            phases across robots in its place. The draw is reported per device in
            `trace_meta.json` under `robot_join`, and `join_frac_max` is a reported setting.

The reason D101 exists is cold-rebuild pressure: starting every history at zero meant no arm
ever had to rebuild a prefix it did not watch being built, which is the cost round 1 is for.

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

# D136: the ratio may now name THREE classes, dashcam:robot:assistive. The two-class forms are
# kept EXACTLY as they were and parse to zero assistive devices, which is what makes the
# byte-identity gate possible: "50:50" is not a new spelling of "50:50:0", it is the same key.
RATIOS = {"50:50": (50, 50), "75:25": (75, 25), "25:75": (25, 75)}
RATIOS_3 = {"50:50:0": (50, 50, 0), "40:40:20": (40, 40, 20),
            # EVAL_PLAN (user, 2026-11-23) composition conditions at 16 devices: dashcam-heavy 10:4:2 and
            # robot-heavy 3:11:2, which round exactly at 16 (`_split_fleet3`). Added keys only; every existing
            # key and trace is unchanged (ratios3_identity_proof.py, digest identity at one sha, two trees).
            "10:4:2": (10, 4, 2), "3:11:2": (3, 11, 2)}
MODES = ("A", "B")

# D136: an assistive question is a SINGLE SHOT. One image, one question, NO HISTORY, so the type
# holds zero residency by construction and cannot exercise warm-state continuity at all. That
# makes it a CONTRAST CLASS rather than a third workload: it is immune to capacity pressure for
# the same structural reason the zero-residency arms are.
# D136: an assistive question reuses the COMMITTED record kinds. It is a single-shot session
# carrying ONE IMAGE as its evidence and one question at L_SS, with NO history_preload and NO
# further batches, so it holds zero residency by construction. Reusing the kinds means the
# emulator, the coordinator and every arm need NO change, which is both the default rule of item
# 4 and what makes the byte-identity gate strong: there are no new branches in the shared path.
OPPORTUNITY_KINDS = ("monitor_opportunity", "recall_question")
TRACE_KINDS = ("device_register", "session_start", "history_preload", "session_end",
               "history_batch", "monitor_opportunity", "recall_question")

# Deadline for a single-shot assistive question. A PARAMETER, swept {1, 2, 3} s per D136 item 3.
DEFAULT_L_SS_S = 2.0
# Arrival period, a parameter (D136 item 1), with a bursty variant switch.
DEFAULT_SS_PERIOD_S = 10.0
SS_BURST_N = 4               # questions per burst in the bursty variant
SS_BURST_GAP_S = 0.5         # spacing inside a burst

# D96 (2): what the canonical fairness digest covers, and the wire kind each trace record maps to.
# `monitor_opportunity` becomes `monitor_frame` in push mode and `monitor_offer` in pull mode;
# monitor_frame in PULL mode is deliberately absent, because the arm's pulls decide which frames
# exist at all.
DIGEST_KINDS = ("device_register", "session_start", "session_end", "history_preload",
                "history_batch", "recall_question", "monitor_opportunity")
MONITOR_WIRE_KIND = {"A": "monitor_frame", "B": "monitor_offer"}

# ---------------------------------------------------------------- D148 / D153: the episode
DASHCAM_FORMATS = ("oneframe", "epg")
# StudySH-EP `sh_ep_manifest.EP_G_CAP_FRAMES` = 21 frames, about 10 s at the 0.5 s cadence. The
# value is retyped here rather than imported, because this module is loaded with only `fleet/`
# on sys.path in some callers and must not reach for the live2 root; `epg_proofs.json` asserts
# it equals the committed constant.
EPG_CAP_FRAMES = 21
# D153's minimum-frame floor, ONE named constant: instants before an episode's Nth frame are
# not decision instants for ANY arm, device or cloud, excluded identically and counted. The
# user may raise it to 6, which is why it is a parameter (`dashcam_min_frames`) with this
# default and not a literal anywhere else.
EPG_MIN_FRAMES = 3
EPG_FLOORS_REPORTED = (3, 6)         # proof (d) reports the excluded count at both
# StudySH-EP's measured EP-G prompt-token law, `prompt_tokens = 42 + 338 * n_frames`. Same
# values as `bodies.EPG_TEXT_TOKENS` / `bodies.EPG_TOK_PER_FRAME`, repeated here for the same
# sys.path reason as EPG_CAP_FRAMES and asserted equal in `epg_proofs.json`.
EPG_TEXT_TOKENS = 42
EPG_TOK_PER_FRAME = 338

EPG_REFRESH_NOTE = (
    "PROVISIONAL (flash, 2026-11-20), the LITERAL reading of D153. D153 says 'fresh context "
    "after N s with no carry-over', which is NOT StudySH-EP's sliding cap: SH-EP capped EP-G at "
    "the last 21 frames and its cap bound exactly at its last instant, so SH-EP never exercised "
    "a refresh at all and cannot settle this. Implemented here as a FRESH CONTEXT EVERY 21 "
    "FRAMES WITH NO CARRY-OVER, N = 21 frames = 10.5 s at the 0.5 s cadence, matching SH-EP's "
    "cap. Measured on the committed seed-4 16-device 1200 s 40:40:20 trace (13,193 monitor "
    "instants, 189 plays): the literal refresh gives a median 10 frames per request, excludes "
    "1,429 instants at floor 3 (10.83 percent) and costs 46,260,494 prompt tokens per run, "
    "against the sliding cap's median 21, 378 exclusions (2.87 percent) and 80,794,968 tokens. "
    "The literal reading is implemented because it is what the D-row says and because it halves "
    "the token load, which matters at 32 devices. A ruling for the sliding cap changes one "
    "function, `_epg_episode`.")

# ---------------------------------------------------------------- D150 SYNC (1) / D154 (4)
# The ROBOT UPLOAD CONTRACT. "batch-30s" is D68 as every committed cell ran it: the session's
# own 30-s grid, one record per window carrying that window's D2 frames. "per-frame" is D150
# SYNC (1) as D154 (4) orders it: one record per frame, offered AT ITS CAPTURE TIME.
#
# It is a property of the TRACE and of nothing else. The frame set, the D2 token accounting
# (`data_sources.d2_batch_tokens`: 90 tokens per 352x256 image plus the 31-token header once per
# session) and the uplink bytes per frame are unchanged; only the PACKAGING and the OFFER TIME
# change. No arm is consulted, so no arm can gain or lose by it, and the cross-arm digest proof
# holds by construction rather than by discipline.
ROBOT_UPLOADS = ("batch-30s", "per-frame")
ROBOT_UPLOAD_DEFAULT = "batch-30s"

ROBOT_UPLOAD_NOTE = (
    "D154 (4) / D150 SYNC (1): robot history frames upload PER FRAME AS CAPTURED, for ALL arms, "
    "replacing D68's fixed 30-s batches. One `history_batch` record per D2 frame, offered at "
    "t0 + the frame's session-local capture time, carrying exactly one frame_ref and one frame's "
    "bytes. The record KIND, its fields and the D2 token accounting are unchanged, so the "
    "emulator, the coordinator, `cstate` and every arm need no change; `cum_tokens` still carries "
    "the session's running total and the 31-token D2 header is still charged once per session, on "
    "its first holding (the D101 preload where there is one, otherwise the first frame). "
    "ONE INTENDED DIFFERENCE BEYOND PACKAGING, named because it is visible in the counts: under "
    "batch-30s a window whose END falls after the run horizon is dropped whole, taking frames "
    "captured BEFORE the horizon with it; per-frame keeps every frame captured before the "
    "horizon, which is the point of the contract. Earlier cells are labelled upload-30s.")

DEFAULT_STAGGER_S = DS.HISTORY_BATCH_S      # 30 s, the D68 history-batch period
ANSWER_PAYLOAD_B = 300                      # a cloud answer body; see links.deliver_s
JOIN_FRAC_MAX = 0.5                         # D101: join ~ U[0, 0.5 x session duration)

# ------------------------------------------------- D242 item A: correlated multi-robot outage
# `k` of the robots lose the uplink together for `D` seconds, then reconnect. ONE window per
# run, the SAME window for every robot in the set, so the loss is CORRELATED and not k
# independent losses. OFF BY DEFAULT (`outage_robots_k = 0`): the block does not run, no stats
# attribute is set and no meta key is added, so a trace built without it is byte-identical to
# the committed one. Same idiom as the D159 (C) re-ask block.
#
# PLACEMENT IS PROVISIONAL AND AWAITS A RULING. D242 says "start chosen deterministically from
# the seed, placed mid-episode", which does not settle whether "mid-episode" is the MIDPOINT or
# a seeded draw inside a middle band. A midpoint needs no seed and would leave
# `outage_seed_offset` with no effect on the start, so the band reading is implemented: a draw
# uniform in [LO, HI] x (run_s - D). Changing the reading changes these two constants and
# nothing else.
OUTAGE_PLACEMENT_LO = 0.25
OUTAGE_PLACEMENT_HI = 0.75

OUTAGE_NOTE = (
    "D242 item A (PROVISIONAL, placement awaiting a ruling): `outage_robots_k` robots drawn "
    "from a dedicated RNG stream keyed on (seed, outage_seed_offset, k, D) lose the uplink "
    "TOGETHER for `outage_duration_s` seconds, in ONE window per run whose start is drawn "
    "uniformly in [%.2f, %.2f] x (run_s - D). INSIDE THE WINDOW NOTHING IS OFFERED. A "
    "`history_batch` record's `t` IS its offer time, so its `t` moves to the reconnect instant "
    "and `fleet/links.py`'s committed UplinkQueue produces the burst and records `queue_s`; no "
    "burst model is written here and links.py is unedited. A `recall_question`'s `t` is the ASK "
    "time and the deadline anchor, so it does NOT move: the question gains `t_offer`, read at "
    "`fleet/emulator.py::_on_recall_question` and handed to UplinkQueue.send, so the question "
    "reaches the cloud only after the reconnect and past its own deadline, and the COMMITTED "
    "standing-answer rule (`scorer/score.py::_standing` / `_standing_by_deadline`) leaves the "
    "DEVICE's answer standing. No second device-only mechanism exists. `device_answers.jsonl` "
    "is untouched, and so are every `opportunity_id` and the monitor and question record order, "
    "because only history offer times move." % (OUTAGE_PLACEMENT_LO, OUTAGE_PLACEMENT_HI))


def _epg_episode(play_id: str, refs: Sequence[str], idx: int,
                 cap_frames: int = EPG_CAP_FRAMES) -> Dict[str, Any]:
    """The append-only episode context at the `idx`-th captured instant of one play (D148).

    Pure, deterministic, and a function of the CAPTURE INDEX alone, so it cannot depend on any
    arm's decisions. `refs` is the play's captured frames in order. The refresh is the literal
    reading of D153 (see EPG_REFRESH_NOTE): a fresh context every `cap_frames` frames with no
    carry-over, so the episode's frames are the current cycle's frames up to and including this
    one, oldest first.
    """
    cycle, pos = divmod(int(idx), int(cap_frames))
    start = cycle * int(cap_frames)
    return dict(episode_id=f"{play_id}|e{cycle:03d}", episode_index=pos,
                frame_refs=list(refs[start:idx + 1]), episode_frames=pos + 1)


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
    """The committed two-class split, UNCHANGED. D136's third class goes through `_split_fleet3`."""
    if ratio not in RATIOS:
        raise ValueError(f"ratio {ratio!r} not in {sorted(RATIOS)} (D67)")
    d, r = RATIOS[ratio]
    n_dash = int(round(n_devices * d / float(d + r)))
    return n_dash, n_devices - n_dash


def _split_fleet3(n_devices: int, ratio: str) -> Tuple[int, int, int]:
    """dashcam : robot : assistive. A two-class ratio yields zero assistive devices.

    The two-class path DELEGATES to `_split_fleet` rather than reimplementing it, so a two-class
    ratio cannot drift from its committed split. That is what the byte-identity gate rests on.
    """
    if ratio in RATIOS:
        n_dash, n_rob = _split_fleet(n_devices, ratio)
        return n_dash, n_rob, 0
    if ratio not in RATIOS_3:
        raise ValueError(f"ratio {ratio!r} not in {sorted(set(RATIOS) | set(RATIOS_3))}")
    d, r, a = RATIOS_3[ratio]
    tot = float(d + r + a)
    n_dash = int(round(n_devices * d / tot))
    n_ass = int(round(n_devices * a / tot))
    return n_dash, n_devices - n_dash - n_ass, n_ass


# ---------------------------------------------------------------- the generator
@dataclass
class TraceStats:
    n_devices: int = 0
    n_dashcam: int = 0
    n_robot: int = 0
    n_assistive: int = 0                 # D136
    assistive_questions_total: int = 0
    assistive_questions_per_device: Dict[str, int] = field(default_factory=dict)
    dashcam_instants: Dict[str, int] = field(default_factory=dict)
    dashcam_meeting_200: int = 0
    dashcam_plays_started: int = 0
    dashcam_plays_completed: int = 0
    robot_questions_total: int = 0
    robot_questions_per_device: Dict[str, int] = field(default_factory=dict)
    robot_sessions_started: int = 0
    robot_sessions_completed: int = 0
    robot_history_batches: int = 0
    # D154 (4): which upload contract this trace was built under, how many upload records the
    # robots sent, and how many FRAMES those records carried. The frame count is the invariant
    # the two modes must agree on inside the run horizon: per-frame upload changes how the same
    # frames are packaged, not which frames the session captures.
    robot_upload: str = "batch-30s"
    robot_history_uploads: int = 0
    robot_history_frames: int = 0
    robot_history_tokens: int = 0
    # D101: the join draw and what the cloud already holds at t = 0, per robot device.
    robot_join_offset_s: Dict[str, float] = field(default_factory=dict)
    robot_preload_frames: Dict[str, int] = field(default_factory=dict)
    robot_preload_tokens: Dict[str, int] = field(default_factory=dict)
    robot_preloads_emitted: int = 0
    robot_questions_before_join: int = 0
    clip_play_counts: Dict[str, int] = field(default_factory=dict)
    session_play_counts: Dict[str, int] = field(default_factory=dict)
    clip_repeats: int = 0
    session_repeats: int = 0
    # D142 item 1: which robot question set this trace drew from, the pool it drew from, and how
    # often a question was asked MORE THAN ONCE in the run. With the LH-REQ pool at 69 questions
    # over 51 sessions against the EVAL pool's 602 over 164, repeats stop being a footnote: the
    # same question reaching several devices is the normal case, and a pooled count that does not
    # say how many DISTINCT questions it covers overstates what the run measured.
    robot_question_set: str = "eval"
    ss_question_set: str = "ss1"
    robot_question_pool_n: int = 0
    robot_session_pool_n: int = 0
    robot_question_ask_counts: Dict[str, int] = field(default_factory=dict)
    robot_distinct_questions_asked: int = 0
    robot_question_repeats: int = 0
    # D153 proof (d). `epg_instants_captured` counts every instant of every play, decision
    # instant or not; `dashcam_instants` keeps its meaning and counts DECISION instants only.
    # The exclusions are counted at BOTH floors the user named, whichever one is applied, so the
    # cost of raising the floor to 6 is readable off a run made at 3.
    dashcam_format: str = "oneframe"
    dashcam_min_frames: int = 0
    epg_instants_captured: int = 0
    epg_episodes: int = 0
    epg_frames_in_requests: int = 0
    epg_excluded_by_floor: Dict[int, int] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        d = dict(self.__dict__)
        if self.epg_instants_captured:
            n_dec = sum(self.dashcam_instants.values())
            d["epg_frames_per_request_mean"] = (
                round(self.epg_frames_in_requests / n_dec, 4) if n_dec else None)
            d["epg_excluded_frac_by_floor"] = {
                k: round(v / self.epg_instants_captured, 6)
                for k, v in sorted(self.epg_excluded_by_floor.items())}
            d["epg_prompt_tokens_total"] = (EPG_TEXT_TOKENS * n_dec
                                            + EPG_TOK_PER_FRAME * self.epg_frames_in_requests)
        d["dashcam_min_instants"] = min(self.dashcam_instants.values()) if self.dashcam_instants \
            else None
        d["robot_pool_meets_20"] = self.robot_questions_total >= 20
        # D82's minimum is POOLED, so it is reported against the pooled count. The distinct count
        # is reported beside it because the two diverge sharply on LH-REQ and a reader comparing
        # arms needs to know whether 20 pooled questions covered 20 questions or 8.
        d["robot_distinct_meets_20"] = self.robot_distinct_questions_asked >= 20
        d["robot_asks_per_distinct_question"] = (
            round(self.robot_questions_total / self.robot_distinct_questions_asked, 4)
            if self.robot_distinct_questions_asked else None)
        d["robot_pool_coverage"] = (
            round(self.robot_distinct_questions_asked / self.robot_question_pool_n, 4)
            if self.robot_question_pool_n else None)
        tok = sorted(self.robot_preload_tokens.values())
        d["robot_preload_tokens_min"] = tok[0] if tok else None
        d["robot_preload_tokens_median"] = tok[len(tok) // 2] if tok else None
        d["robot_preload_tokens_max"] = tok[-1] if tok else None
        d["robot_preload_tokens_total"] = sum(tok) if tok else 0
        return d


def generate_trace(seed: int, n_devices: int, ratio: str, run_s: float, mode: str,
                   stagger_s: float = DEFAULT_STAGGER_S,
                   frame_manifest: Optional[Path] = None,
                   count_only: bool = False,
                   l_ss_s: float = DEFAULT_L_SS_S,
                   ss_period_s: float = DEFAULT_SS_PERIOD_S,
                   ss_bursty: bool = False,
                   robot_question_set: str = "eval",
                   ss_question_set: str = "ss1",
                   dashcam_format: str = "oneframe",
                   dashcam_min_frames: int = EPG_MIN_FRAMES,
                   robot_upload: str = ROBOT_UPLOAD_DEFAULT,
                   robot_reask_mean_s: float = 0.0,
                   outage_robots_k: int = 0,
                   outage_duration_s: float = 0.0,
                   outage_seed_offset: int = 0) -> Dict[str, Any]:
    """Build one run's opportunity trace. Returns {records, device_answers, meta, stats}.

    `dashcam_format="epg"` is D153's append-only episode context (D148). It adds the episode
    fields to every `monitor_opportunity` and drops the instants below `dashcam_min_frames`,
    which are not decision instants for ANY arm. "oneframe" is the default and changes nothing.

    `robot_upload="per-frame"` is D154 (4) / D150 SYNC (1): one `history_batch` record per D2
    frame, offered at its capture time, instead of D68's 30-s windows (see ROBOT_UPLOAD_NOTE).
    "batch-30s" is the default and changes nothing.

    `outage_robots_k`, `outage_duration_s` and `outage_seed_offset` are D242 item A's correlated
    multi-robot outage (see OUTAGE_NOTE). OFF by default, and off means the block below does not
    run at all: no record moves, no stats attribute is set and no meta key is added.

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
    if dashcam_format not in DASHCAM_FORMATS:
        raise ValueError(f"dashcam_format {dashcam_format!r} not in {DASHCAM_FORMATS} (D153)")
    if robot_upload not in ROBOT_UPLOADS:
        raise ValueError(f"robot_upload {robot_upload!r} not in {ROBOT_UPLOADS} (D154 (4))")
    if int(outage_robots_k) < 0 or float(outage_duration_s) < 0.0:
        raise ValueError("outage_robots_k and outage_duration_s must be non-negative (D242 A)")
    per_frame = robot_upload == "per-frame"
    epg = dashcam_format == "epg"
    floor = int(dashcam_min_frames)
    if epg and not 1 <= floor <= EPG_CAP_FRAMES:
        raise ValueError(f"dashcam_min_frames {floor} outside 1..{EPG_CAP_FRAMES}")
    n_dash, n_rob, n_ass = _split_fleet3(n_devices, ratio)

    clips = DS.nexar_clip_meta()
    # D142 item 1 / D143 ruling A: "eval" is the committed default and its trace is byte-identical
    # to every run before this parameter existed. "lh_req" restricts robots to the long-horizon
    # questions on the EVAL split and drops sessions that carry none, so the POOL changes too and
    # the session-repeat counters below are the thing to read, not an afterthought.
    sessions = DS.robot_sessions(robot_question_set)
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
    rng_join = random.Random(f"{seed}|join")      # D101, its own stream

    dash_ids = [f"dash{i:03d}" for i in range(n_dash)]
    rob_ids = [f"robo{i:03d}" for i in range(n_rob)]
    ass_ids = [f"asst{i:03d}" for i in range(n_ass)]

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
    st = TraceStats(n_devices=n_devices, n_dashcam=n_dash, n_robot=n_rob,
                    dashcam_format=dashcam_format,
                    dashcam_min_frames=(floor if epg else 0),
                    epg_excluded_by_floor=({f: 0 for f in EPG_FLOORS_REPORTED} if epg else {}))

    # start_t is drawn in a FIXED device order so the draw does not depend on the ratio split.
    # D101: only the DASHCAM draw is used. The robot draw is still taken, so the dashcam
    # stagger of a given seed is unchanged by D101 and the two builds' dashcam streams stay
    # comparable; a robot's own offset is its join point instead (see below).
    # D136: `ass_ids` is appended LAST so the dashcam and robot draws consume `rng_stag` in
    # exactly the order they did before. For a two-class ratio `ass_ids` is empty and this
    # expression is literally unchanged, which is what keeps the stagger byte-identical.
    start_t = {did: rng_stag.uniform(0.0, stagger_s) for did in dash_ids + rob_ids + ass_ids}
    for did in rob_ids:
        start_t[did] = 0.0

    # D101: the join FRACTION is drawn per robot in a fixed device order, so the k-th robot gets
    # the same draw at every ratio; the OFFSET is that fraction of its own first session.
    join_frac = {did: rng_join.uniform(0.0, JOIN_FRAC_MAX) for did in rob_ids}
    join_offset: Dict[str, float] = {}
    join_meta: Dict[str, Dict[str, Any]] = {}
    for i, did in enumerate(rob_ids):
        first = sess_plan[i][0]
        dur0 = sessions[first].duration_s
        join_offset[did] = join_frac[did] * dur0
        join_meta[did] = dict(join_frac=round(join_frac[did], 9),
                              join_offset_s=round(join_offset[did], 6),
                              first_session=first, first_session_duration_s=round(dur0, 6))

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
            play_instants = DS.nexar_instants(cm.duration_s)
            # the frame_ref literal is the D91 encoder's own rule, asserted as a SOURCE string
            # by tests/test_live2_fix2.py, so it is spelled here exactly as it was spelled
            play_refs = [f"{clip}|t{t_local:07.2f}" for t_local in play_instants]
            pending_b = 0            # bytes of frames captured but not yet charged an upload
            for idx, t_local in enumerate(play_instants):
                t_run = t + t_local
                if t_run > run_s + 1e-9:
                    break
                frame_ref = play_refs[idx]
                nb = frame_bytes_by_ref.get(frame_ref, default_frame_bytes)
                ep = _epg_episode(play_id, play_refs, idx) if epg else None
                if epg:
                    # Every captured frame is charged to the uplink exactly once, and the charge
                    # lands on the first DECISION instant at or after its capture. So the two
                    # instants below the floor are not lost bytes: their frames go up with the
                    # floor instant's request, which is the request that first carries them.
                    pending_b += nb
                    st.epg_instants_captured += 1
                    for fl in EPG_FLOORS_REPORTED:
                        if ep["episode_frames"] < fl:
                            st.epg_excluded_by_floor[fl] = st.epg_excluded_by_floor.get(fl, 0) + 1
                    if ep["episode_index"] == 0:
                        st.epg_episodes += 1
                    if ep["episode_frames"] < floor:
                        continue
                    nb, pending_b = pending_b, 0
                    st.epg_frames_in_requests += ep["episode_frames"]
                if not count_only:
                    key = (clip, round(t_local, 6))
                    if key not in orin:
                        raise DS.MissingInput(
                            f"no committed Orin device score for instant {key}; the dense "
                            f"StudyORIN1 set does not cover this clip at this cadence")
                    o = orin[key]
                    opp = f"{play_id}|t{t_local:07.2f}"
                    rec = dict(kind="monitor_opportunity", device_id=did,
                               opportunity_key=opp, instant_id=opp, play_id=play_id,
                               clip=clip, t=round(t_run, 6),
                               t_local=round(t_local, 6),
                               deadline_s=DS.NEXAR_DEADLINE_S, frame_ref=frame_ref,
                               frame_bytes=nb, play_completed=completed)
                    if epg:
                        rec.update(ep)
                    records.append(rec)
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

    # ---------------------------------------------------------------- D136: assistive devices
    # SINGLE SHOT. Each question is its own session: session_start, ONE history_batch carrying the
    # single image, the question at L_SS, session_end. No preload and no further batches, so there
    # is no accumulated history and the type holds ZERO RESIDENCY by construction.
    #
    # That makes it a CONTRAST CLASS rather than a third workload: it cannot exercise warm-state
    # continuity at all, which is the cleanest available control for whether warm state is what
    # matters. It is immune to capacity pressure for the same structural reason the zero-residency
    # arms are.
    #
    # `history_batch` rather than `history_preload`: the image is captured AT QUESTION TIME, so it
    # must be charged uplink. D101's preload is explicitly free because those frames were already
    # on cloud-side disk before the clock started, which is not true here.
    #
    # The whole block is inside `if ass_ids`, EMPTY for every two-class ratio, so an existing
    # trace takes not one new branch.
    if ass_ids:
        # D143: "ss1" is the committed default and its trace is byte-identical to every run before
        # this parameter existed. "ss2" draws from RefSpatial-Bench and RealWorldQA, and ONLY from
        # the EVAL part of the committed seeded 30 / 70 split, because the SS quality table is
        # fitted on the DEV part.
        pool = [] if count_only else DS.ss_questions(ss_question_set, "eval")
        for idx, did in enumerate(ass_ids):
            if not count_only:
                records.append(dict(kind="device_register", device_id=did, type="assistive",
                                    uplink_mbps=None, rtt_ms=None,
                                    start_t=round(start_t[did], 6)))
            t = start_t[did]
            cursor = 0
            n_q = 0
            while t < run_s:
                times = ([t + b * SS_BURST_GAP_S for b in range(SS_BURST_N)]
                         if ss_bursty else [t])
                for tq in times:
                    if tq >= run_s:
                        break
                    if not count_only:
                        q = pool[(idx * 997 + cursor) % len(pool)]
                        sid = f"{did}|ss{cursor:04d}"
                        tok = int(q["prompt_tokens"])
                        records.append(dict(kind="session_start", device_id=did, session_id=sid,
                                            t=round(tq, 6), source_session=q["qid"],
                                            duration_s=float(l_ss_s), join_offset_s=0.0,
                                            joined_part_way=False))
                        records.append(dict(kind="history_batch", device_id=did, session_id=sid,
                                            batch_id=f"{sid}|b000", t=round(tq, 6),
                                            frame_refs=[f"{q['qid']}|img"],
                                            est_tokens=tok, cum_tokens=tok,
                                            frame_bytes=int(q["image_bytes"])))
                        records.append(dict(kind="recall_question", device_id=did, session_id=sid,
                                            opportunity_key=sid, question_id=q["qid"],
                                            t=round(tq, 6), t_ask_session=0.0,
                                            deadline_s=float(l_ss_s), question=q["question"],
                                            options=[], gold_letter=None,
                                            category=q["dataset"], history_tokens=tok))
                        records.append(dict(kind="session_end", device_id=did, session_id=sid,
                                            t=round(min(tq + float(l_ss_s), run_s), 6)))
                        answers.append(dict(opportunity_key=sid, device_id=did, kind="assistive",
                                            question_id=q["qid"],
                                            device_answer=q["device_answer"],
                                            device_score=q["device_score"],
                                            device_model=q["device_model"],
                                            device_host=q["device_host"]))
                    cursor += 1
                    n_q += 1
                t += float(ss_period_s)
            st.assistive_questions_per_device[did] = n_q
            st.assistive_questions_total += n_q
    st.n_assistive = len(ass_ids)

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
            # D101: the FIRST session of a robot is joined `join` seconds in; every later
            # session in the chain starts from zero (D83). `t0` is the session's virtual origin
            # on the run clock, so for a joined first session t0 = -join.
            join = join_offset[did] if k == 0 else 0.0
            t0 = t - join
            if not count_only:
                records.append(dict(kind="session_start", device_id=did, session_id=play_id,
                                    t=round(t, 6), source_session=sid,
                                    duration_s=round(sm.duration_s, 6),
                                    join_offset_s=round(join, 6),
                                    joined_part_way=bool(join > 0.0)))
            # D83: a new session is a new task, so history restarts from zero here.
            b = 0
            emitted = 0
            tokens_sent = 0
            # D101: what the cloud ALREADY HOLDS at t = 0 for a joined session. No uplink time
            # is charged for it (the frames were on cloud-side disk before the clock started),
            # and it is the session's FIRST holding, so it carries the D2 header once.
            pre_fr = DS.d2_frames_in(0.0, join) if join > 0.0 else []
            if pre_fr:
                pre_tok = DS.d2_batch_tokens(len(pre_fr), first_batch=True)
                emitted = 1
                tokens_sent = pre_tok
                st.robot_preloads_emitted += 1
                if not count_only:
                    records.append(dict(kind="history_preload", device_id=did,
                                        session_id=play_id, t=0.0,
                                        frame_refs=[f"{sid}|f{x:08.2f}" for x in pre_fr],
                                        est_tokens=pre_tok, cum_tokens=pre_tok,
                                        join_offset_s=round(join, 6), uplink_charged=False))
            if k == 0:
                st.robot_join_offset_s[did] = round(join, 6)
                st.robot_preload_frames[did] = len(pre_fr)
                st.robot_preload_tokens[did] = tokens_sent
            if per_frame:
                # D154 (4) / D150 SYNC (1). ONE RECORD PER FRAME, offered at the frame's own
                # capture time. The frame set is `d2_frames_in(join, duration)`, which is
                # exactly the union of the windows the batch branch below walks, so no frame is
                # added or dropped by the contract; the D2 header is charged once per session by
                # the same `emitted == 0` rule the batch branch uses.
                for i, x in enumerate(DS.d2_frames_in(join, sm.duration_s)):
                    t_offer = t0 + x
                    if t_offer > run_s + 1e-9:
                        break
                    tok = DS.d2_batch_tokens(1, first_batch=(emitted == 0))
                    emitted += 1
                    tokens_sent += tok
                    if not count_only:
                        records.append(dict(kind="history_batch", device_id=did,
                                            session_id=play_id,
                                            batch_id=f"{play_id}|u{i:05d}",
                                            t=round(t_offer, 6),
                                            frame_refs=[f"{sid}|f{x:08.2f}"],
                                            est_tokens=tok, cum_tokens=tokens_sent,
                                            frame_bytes=default_hist_frame_bytes))
                    st.robot_history_batches += 1
                    st.robot_history_uploads += 1
                    st.robot_history_frames += 1
                    st.robot_history_tokens += tok
            else:
              # D68, the COMMITTED branch, unchanged and deliberately left at its own
              # indentation so the diff shows no reformatting of a committed code path.
              while True:
                b += 1
                w_from = (b - 1) * DS.HISTORY_BATCH_S
                w_to = min(b * DS.HISTORY_BATCH_S, sm.duration_s)
                if w_from >= sm.duration_s - 1e-9:
                    break
                # D101: the batch grid is the session's own 30-s grid and is unchanged by the
                # join; a batch carries only the frames the preload did not already hold, so no
                # frame is ever counted twice and none is dropped.
                fr = DS.d2_frames_in(max(w_from, join), w_to)
                t_offer = t0 + w_to
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
                st.robot_history_uploads += 1
                st.robot_history_frames += len(fr)
                st.robot_history_tokens += tok
                if w_to >= sm.duration_s - 1e-9:
                    break
            for q in sm.questions:
                if q.t_ask > sm.duration_s + 1e-9:
                    continue
                # D101: a question before the join point is NOT emitted and NOT counted.
                if q.t_ask < join - 1e-9:
                    st.robot_questions_before_join += 1
                    continue
                t_run = t0 + q.t_ask
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
                st.robot_question_ask_counts[q.question_id] = (
                    st.robot_question_ask_counts.get(q.question_id, 0) + 1)
                nq += 1
            t_end = t0 + sm.duration_s
            if t_end <= run_s + 1e-9:
                if not count_only:
                    records.append(dict(kind="session_end", device_id=did,
                                        session_id=play_id, t=round(t_end, 6)))
                st.robot_sessions_completed += 1
            t = t_end
        st.robot_questions_per_device[did] = nq
    st.robot_questions_total = sum(st.robot_questions_per_device.values())
    st.robot_upload = robot_upload
    st.robot_question_set = robot_question_set
    st.ss_question_set = ss_question_set
    st.robot_question_pool_n = sum(len(sm.questions) for sm in sessions.values())
    st.robot_session_pool_n = len(sessions)
    st.robot_distinct_questions_asked = len(st.robot_question_ask_counts)
    st.robot_question_repeats = sum(v - 1 for v in st.robot_question_ask_counts.values() if v > 1)
    st.session_repeats = sum(v - 1 for v in st.session_play_counts.values() if v > 1)

    # ------------------------------------------------------------------ D159 (C) / D161 re-asks
    # OFF BY DEFAULT (`robot_reask_mean_s = 0.0`), so a trace built without it is byte-identical
    # to the committed one: the block does not run at all.
    #
    # D159 (C): per robot device a Poisson re-ask process, drawing UNIFORMLY from that session's
    # questions ALREADY ASKED, originals left at their real times, gold unchanged. D161 (1)
    # confirmed the already-asked draw pool after the measurement showed no recoverable reservoir.
    #
    # The RNG is a DEDICATED stream keyed on (seed, device), never the generator's own `rng`, so
    # turning re-asks on cannot perturb any other part of the trace. It is a pure function of the
    # seed and the device id, so every arm given the same cell arguments gets the same re-asks,
    # which is what the fairness digest then proves rather than assumes.
    if robot_reask_mean_s and float(robot_reask_mean_s) > 0.0 and not count_only:
        mean_s = float(robot_reask_mean_s)
        warm_lat = DS.device_recall_warm_latency_s()
        # session spans in WALL CLOCK, from the records the loop above already emitted
        # t0 is the session's OWN episode clock origin on the run clock, and it is NOT the
        # session_start record's t: a joined session (D101) starts its episode before the run
        # window, so session_start is clamped at the join while the episode clock began earlier.
        # Taking t0 from session_start made t_ask_session disagree with the originals' own values
        # (measured: an original with t=156.677541 carries t_ask_session=164.0, so t0=-7.32), which
        # would put the re-ask's history window and the Orin's recent window on the wrong clock.
        # t0 is therefore derived from an ORIGINAL ask, using the generator's own accounting.
        span = {}
        for r in records:
            if r["kind"] == "session_end" and str(r["device_id"]).startswith("robo"):
                span.setdefault(r["session_id"], {})["t_end"] = float(r["t"])
        asked = {}
        for r in records:
            if r["kind"] == "recall_question" and str(r["device_id"]).startswith("robo"):
                asked.setdefault(r["session_id"], []).append(r)
        extra, n_beyond_32k, n_no_pool = [], 0, 0
        for sid in sorted(asked):
            sp = span.get(sid) or {}
            originals = sorted(asked[sid], key=lambda r: float(r["t"]))
            o0 = originals[0]
            t0 = float(o0["t"]) - float(o0["t_ask_session"])
            # a session truncated by the run horizon has no session_end record
            t_end = min(float(sp.get("t_end", run_s)), float(run_s))
            dur_s = t_end - t0
            if dur_s <= 0:
                continue
            dev = originals[0]["device_id"]
            rr = random.Random("reask|%d|%s|%s" % (int(seed), dev, sid))
            t = float(originals[0]["t"])          # the first ask opens the eligible window
            k = 0
            while True:
                t = t + rr.expovariate(1.0 / mean_s)
                if t > t_end + 1e-9:
                    break
                pool = [o for o in originals if float(o["t"]) <= t + 1e-9]
                if not pool:
                    n_no_pool += 1
                    continue
                src = pool[rr.randrange(len(pool))]
                k += 1
                t_sess = t - t0
                # the history the CLOUD holds AT THE RE-ASK, by the same D2 accounting the
                # original ask used (`fleet/trace.py` robot loop), recomputed for the later time.
                nfr = len(DS.d2_frames_in(0.0, min(t_sess, dur_s)))
                hist_tok = DS.d2_batch_tokens(nfr, first_batch=True)
                if hist_tok > 32_000:
                    n_beyond_32k += 1          # D159 (C): COUNT, never truncate
                qid = src["question_id"]
                opp = "%s|%s#r%d" % (sid, qid, k)
                extra.append(dict(kind="recall_question", device_id=dev, session_id=sid,
                                  opportunity_key=opp, question_id=qid,
                                  t=round(t, 6), t_ask_session=round(t_sess, 6),
                                  deadline_s=DS.ROBOT_DEADLINE_S, question=src["question"],
                                  options=src["options"], gold_letter=src["gold_letter"],
                                  category=src["category"], history_tokens=hist_tok,
                                  reask_of=src["opportunity_key"], reask_index=k))
                da = dev_answers[qid]
                # D161 (3): the device latency on a re-ask is the RECENT-WINDOW WARM measurement
                # (D155 / StudyORIN-REC WARM), NOT `device_recall_latency_s(hist_tok)`, which
                # grows with history. The SCORER already prefers the measured table keyed on
                # question_id and REFUSES rather than guessing (`scorer/score.py:248-258`), so the
                # scored quantity was already correct; this makes the trace's own superseded
                # fallback field agree with it instead of contradicting it.
                answers.append(dict(opportunity_key=opp, device_id=dev, kind="recall",
                                    session_id=sid, question_id=qid,
                                    device_answer=da["pred"], device_correct=da["correct"],
                                    gold_letter=da["gold"],
                                    device_latency_s=float(warm_lat[qid]),
                                    history_tokens=hist_tok, reask_index=k))
                st.robot_question_ask_counts[qid] = st.robot_question_ask_counts.get(qid, 0) + 1
        records.extend(extra)
        st.robot_reask_mean_s = mean_s
        st.robot_reasks_emitted = len(extra)
        st.robot_reasks_beyond_32k = n_beyond_32k
        st.robot_reask_empty_pool = n_no_pool
        st.robot_questions_total = sum(st.robot_questions_per_device.values()) + len(extra)
        st.robot_distinct_questions_asked = len(st.robot_question_ask_counts)
        st.robot_question_repeats = sum(v - 1 for v in st.robot_question_ask_counts.values()
                                       if v > 1)

    # ------------------------------------------------ D242 item A: correlated robot outage
    # OFF BY DEFAULT. See OUTAGE_NOTE for the rule and for what is deliberately NOT changed.
    # The schedule is computed and applied here, BEFORE the canonical sort, so the moved
    # history offers take their new place in the trace's canonical order. Only `history_batch`
    # records move, and `history_batch` is not an opportunity kind, so the relative order of
    # the `monitor_opportunity` and `recall_question` records is unchanged and every
    # `opportunity_id` below is assigned exactly as it would have been with the outage off.
    outage_meta: Optional[Dict[str, Any]] = None
    outage_q_keys: List[str] = []
    if int(outage_robots_k) > 0 and float(outage_duration_s) > 0.0:
        k_out = int(outage_robots_k)
        d_out = float(outage_duration_s)
        if k_out > len(rob_ids):
            raise ValueError("outage_robots_k %d exceeds the %d robot devices in this fleet"
                             % (k_out, len(rob_ids)))
        if d_out >= float(run_s):
            raise ValueError("outage_duration_s %g does not fit inside run_s %g"
                             % (d_out, float(run_s)))
        # A DEDICATED RNG STREAM, keyed on (seed, offset, k, D) and never the generator's own,
        # so turning the outage on cannot perturb one other draw in the trace.
        rng_out = random.Random("outage|%d|%d|%d|%.6f"
                                % (int(seed), int(outage_seed_offset), k_out, d_out))
        victims = sorted(rng_out.sample(sorted(rob_ids), k_out))
        span = float(run_s) - d_out
        t_out0 = rng_out.uniform(OUTAGE_PLACEMENT_LO * span, OUTAGE_PLACEMENT_HI * span)
        t_out1 = t_out0 + d_out
        vset = set(victims)
        n_def_rec = n_def_frames = n_def_est_tokens = 0
        per_robot: Dict[str, Dict[str, int]] = {v: dict(records=0, frames=0) for v in victims}
        for r in records:
            if str(r.get("device_id")) not in vset:
                continue
            t_r = float(r.get("t", 0.0))
            if not (t_out0 <= t_r < t_out1):
                continue
            if r["kind"] == "history_batch":
                # `t` IS the offer time for a history record (the generator's own `t_offer`), so
                # moving it to the reconnect instant is the WHOLE change on this path: the
                # committed UplinkQueue then takes t_start = max(offer, free_at) and records the
                # queueing delay it imposed. Nothing here models a burst.
                r["t"] = round(t_out1, 6)
                n_def_rec += 1
                n_def_frames += len(r.get("frame_refs") or ())
                n_def_est_tokens += int(r["est_tokens"])
                per_robot[str(r["device_id"])]["records"] += 1
                per_robot[str(r["device_id"])]["frames"] += len(r.get("frame_refs") or ())
            elif r["kind"] == "recall_question":
                # `t` is the ASK time and the deadline anchor and MUST NOT move. Only the OFFER
                # moves, in its own field, and the READ that makes it causal is
                # `fleet/emulator.py::_on_recall_question`, which hands this value to
                # UplinkQueue.send in place of the event time.
                r["t_offer"] = round(t_out1, 6)
                outage_q_keys.append(r["opportunity_key"])
        outage_meta = dict(
            args=dict(outage_robots_k=k_out, outage_duration_s=d_out,
                      outage_seed_offset=int(outage_seed_offset)),
            robots=victims, n_robots_total=len(rob_ids),
            t_start=round(t_out0, 6), t_end=round(t_out1, 6), duration_s=d_out,
            placement_rule=("seeded uniform draw in [%.2f, %.2f] x (run_s - D); PROVISIONAL, "
                            "see OUTAGE_NOTE" % (OUTAGE_PLACEMENT_LO, OUTAGE_PLACEMENT_HI)),
            rng_stream_key="outage|%d|%d|%d|%.6f" % (int(seed), int(outage_seed_offset),
                                                     k_out, d_out),
            deferred_history_records=n_def_rec, deferred_history_frames=n_def_frames,
            deferred_history_est_tokens=n_def_est_tokens,
            backlog_tokens_d2=n_def_frames * DS.D2_TOK_PER_IMG,
            deferred_per_robot=per_robot,
            device_only_questions=len(outage_q_keys),
            rule=OUTAGE_NOTE)
        st.outage_robots_k = k_out
        st.outage_duration_s = d_out
        st.outage_seed_offset = int(outage_seed_offset)
        st.outage_robots = victims
        st.outage_t_start = round(t_out0, 6)
        st.outage_t_end = round(t_out1, 6)
        st.outage_deferred_history_records = n_def_rec
        st.outage_deferred_history_frames = n_def_frames
        st.outage_backlog_tokens_d2 = n_def_frames * DS.D2_TOK_PER_IMG
        st.outage_device_only_questions = len(outage_q_keys)

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
    # D159 (C) / D161: a re-ask carries `reask_of`, which held the ORIGINAL's opportunity_key.
    # That key has just been popped, so translate the reference to the assigned opportunity_id or
    # it would dangle. Done here, in the same place and from the same map, so the two cannot drift.
    for r in records:
        if "reask_of" in r:
            r["reask_of"] = assigned[r["reask_of"]]
    # D242 item A: the deferred questions were collected by `opportunity_key`, which has just
    # been popped, so they are translated here from the SAME map for the same reason.
    if outage_meta is not None:
        outage_meta["device_only_question_ids"] = sorted(assigned[k] for k in outage_q_keys)

    meta = dict(robot_question_set=robot_question_set, ss_question_set=ss_question_set,
                robot_upload=robot_upload,
                robot_upload_rule=(ROBOT_UPLOAD_NOTE if per_frame else
                                   "D68: robot history frames upload in fixed %.0f-s batches on "
                                   "the session's own grid (upload-30s, the committed contract)."
                                   % DS.HISTORY_BATCH_S),
                dashcam_format=dashcam_format,
                dashcam_min_frames=(floor if epg else None),
                epg_cap_frames=(EPG_CAP_FRAMES if epg else None),
                epg_refresh_rule=(EPG_REFRESH_NOTE if epg else None),
                epg_floor_rule=(
                    "D153: an instant whose episode holds fewer than %d frames is NOT a "
                    "decision instant for any arm, device or cloud. Such instants are "
                    "excluded identically, by not being emitted as opportunities at all, so no "
                    "arm can see them and the exclusion cannot differ by arm. Their frames are "
                    "still CAPTURED and still enter the "
                    "episode context, and their uplink bytes are charged to the first decision "
                    "instant that carries them." % floor) if epg else None,
                seed=seed, n_devices=n_devices, ratio=ratio, run_s=run_s, mode=mode,
                stagger_s=stagger_s, n_dashcam=n_dash, n_robot=n_rob,
                n_assistive=n_ass, l_ss_s=float(l_ss_s),
                ss_period_s=float(ss_period_s), ss_bursty=bool(ss_bursty),
                ss_device_answer_host="unconfirmed",
                ss_device_answer_source=("StudySS1 8492e02; NO _provenance block in any of the five artifacts, endpoint is localhost, so the brief's Orin 4B attribution cannot be confirmed from the file and Orin against an A6000 proxy is a different device tier"),
                cadence_s=DS.NEXAR_INSTANT_CADENCE_S,
                dashcam_deadline_s=DS.NEXAR_DEADLINE_S,
                robot_deadline_s=DS.ROBOT_DEADLINE_S,
                # D154 (4): the 30-s period is a property of the batch-30s contract alone, so
                # a per-frame trace carries None here rather than a number that does not apply.
                history_batch_s=(None if per_frame else DS.HISTORY_BATCH_S),
                robot_join_frac_max=JOIN_FRAC_MAX,
                robot_join=join_meta,
                robot_join_rule=(
                    "D101: each robot joins its FIRST session at a seeded point drawn uniformly "
                    "in [0, 0.5 x session duration); questions before the join point are not "
                    "emitted and not counted; at t = 0 a history_preload declares the frames "
                    "the cloud already holds, with NO uplink time charged; later sessions in "
                    "the chain start from zero (D83). Dashcam devices keep the run-time "
                    "stagger and the complete-play rule (D85)."),
                frame_bytes_source=frame_bytes_source, count_only=count_only,
                answer_payload_bytes=ANSWER_PAYLOAD_B,
                trace_label="NOT A MEASUREMENT: a deterministic device script",
                mode_affects_trace=False,
                caveats=[DS.AP_CAVEAT, DS.DEVICE_ANSWER_CAVEAT, DS.SEMBER_JPEG_CAVEAT])
    # D242 item A: the key is ADDED ONLY WHEN THE OUTAGE IS ON. A `None`-valued key would move
    # one byte of trace_meta.json on the default path and break the identity gate, so the
    # schedule travels as a key that is absent rather than as a key that is null.
    if outage_meta is not None:
        meta["outage"] = outage_meta
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
    if k == "history_preload":
        # D101: no batch_id, so the SESSION is the key and the holding's size is the extra
        # field. Byte-identical to the coordinator side's row (live2/traces.py).
        return (dev, "history_preload", f"{float(r['t']):.6f}", str(r["session_id"]),
                str(int(r["est_tokens"])), "")
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
    ap.add_argument("--dashcam-format", default="oneframe", choices=list(DASHCAM_FORMATS),
                    help="D153: 'epg' is the append-only episode context of D148")
    ap.add_argument("--dashcam-min-frames", type=int, default=EPG_MIN_FRAMES,
                    help="D153's minimum-frame floor; epg only")
    ap.add_argument("--outage-robots-k", type=int, default=0,
                    help="D242 A: robots that lose the uplink together; 0 is off")
    ap.add_argument("--outage-duration-s", type=float, default=0.0,
                    help="D242 A: the window D in seconds; 0 is off")
    ap.add_argument("--outage-seed-offset", type=int, default=0,
                    help="D242 A: offsets the dedicated outage RNG stream only")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    b = generate_trace(a.seed, a.devices, a.ratio, a.run_s, a.mode, a.stagger_s,
                       Path(a.frame_manifest) if a.frame_manifest else None,
                       dashcam_format=a.dashcam_format,
                       dashcam_min_frames=a.dashcam_min_frames,
                       # D242 A: forwarded unconditionally HERE because this entry point has no
                       # committed trace to keep byte-identical; the defaults are the off values.
                       outage_robots_k=a.outage_robots_k,
                       outage_duration_s=a.outage_duration_s,
                       outage_seed_offset=a.outage_seed_offset)
    meta = write_trace(Path(a.out), b)
    print(json.dumps(meta, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
