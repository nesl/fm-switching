#!/usr/bin/env python3
"""Where every round-1 input comes from, and a loud failure when it is not there.

StudyLIVE2-fleet, part 1. CPU only. Nothing in this module invents, synthesises or substitutes
data: every loader either returns a committed artefact or raises `MissingInput`, which is the
stop condition the brief sets for part 1.

THE COMMITTED CONSTANTS THIS MODULE CARRIES (each with its source)

  NEXAR_INSTANT_CADENCE_S = 0.5   StudyCTRL1c's decision instant. CTRL1c's definition audit
                                  records "a 'turn' as a decision instant on the 0.5-s cadence";
                                  the underlying score grid is 0.25 s from t = 3.0 s (StudyE9b
                                  `STEP_DENSE`, `T0`).
  NEXAR_GRID_STEP_S       = 0.25  StudyE9b `STEP_DENSE`: the grid the streaming AP is defined on.
  NEXAR_GRID_T0_S         = 3.0   StudyE9b `T0`.
  ORIN_CALIB_A / _B               StudyORIN2-stack's per-tier calibration map.
  D2_TOK_PER_IMG          = 90    StudyRH4: D2 = fixed stride 2 s at 352x256, 90 tok/img.
  D2_STRIDE_S             = 2.0   StudyRH4.
  D2_HEADER_TOK           = 31    StudyRH4's D2 header text.
  E10A_NEXAR_Q            = 90    StudyE10a-jpeg, Nexar.
  E10A_SEMBER_Q           = 88    StudyE10a-jpeg / E10a-full, S-EMBER.
  E10A_NEXAR_Q90_MEDIAN_B         StudyE10a Job A, 768x432, median JPEG q90 bytes per frame.
  E10A_SEMBER_Q88_D2_MEDIAN_B     StudyE10a Job A, 352x256 D2, median JPEG q88 bytes per frame.
"""
from __future__ import annotations

import collections
import gzip
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]

NEXAR_INSTANT_CADENCE_S = 0.5
NEXAR_GRID_STEP_S = 0.25
NEXAR_GRID_T0_S = 3.0
NEXAR_DEADLINE_S = 1.0          # D62/D71: L for a monitoring instant
ROBOT_DEADLINE_S = 5.0          # D68/D71: L for a recall question

ORIN_CALIB_A = 0.114932         # StudyORIN2-stack
ORIN_CALIB_B = 1.174287         # StudyORIN2-stack

D2_TOK_PER_IMG = 90             # StudyRH4
D2_STRIDE_S = 2.0               # StudyRH4
D2_HEADER_TOK = 31              # StudyRH4
HISTORY_BATCH_S = 30.0          # D68

E10A_NEXAR_Q = 90
E10A_SEMBER_Q = 88
E10A_NEXAR_Q90_MEDIAN_B = 63_897.5          # StudyE10a Job A (results/cost/study_e10/e10a_sizes.json)
E10A_SEMBER_Q88_D2_MEDIAN_B = 24_570.0      # StudyE10a Job A, D2 352x256

# Committed artefacts that ARE in the repository.
D14B_TRACE = ROOT / "results/dashcam/study_d14b/d14b_trace_h100nvl.jsonl.gz"
D14_TRACE = ROOT / "results/dashcam/study_d14_trace/d14_trace_h100nvl.jsonl.gz"

# Data drops that are NOT in the repository and are NOT on the flash box. Resolved from the
# environment so the same code runs on whichever host holds them.
NEXAR_FRAME_DIR = Path(os.environ.get(
    "FM_NEXAR_FRAMES", str(Path.home() / "data/dashcam/d14_frames/small")))
D15_FRAME_DIR = Path(os.environ.get("FM_D15_FRAMES", "/home/nesl/data/d14_n1"))
SEMBER_FRAME_CACHE = Path(os.environ.get(
    "FM_SEMBER_FRAMES", str(Path.home() / ".cache/fm-switching/sember_frames")))
SEMBER_R1_INPUTS = Path(os.environ.get(
    "FM_SEMBER_R1_INPUTS", str(Path.home() / ".cache/fm-switching/r1_inputs")))


class MissingInput(RuntimeError):
    """A part-1 input is absent. The brief's rule: stop and report, never substitute."""


def require(path: Path, what: str, how: str = "") -> Path:
    if not path.exists():
        raise MissingInput(f"MISSING: {what}\n  expected at: {path}\n  {how}".rstrip())
    return path


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def describe(path: Path, what: str) -> Dict[str, Any]:
    """The provenance row the report needs: path, existence, bytes, sha256."""
    row: Dict[str, Any] = dict(what=what, path=str(path), exists=path.exists())
    if path.exists() and path.is_file():
        row["bytes"] = path.stat().st_size
        row["sha256"] = sha256_of(path)
    return row


# ------------------------------------------------------------------ Nexar clips
@dataclass
class ClipMeta:
    clip: str
    label: str              # "positive" | "negative"
    duration_s: float
    event_s: Optional[float]
    grid_points: int        # G on the 0.25-s grid from t = 3.0 s


def nexar_clip_meta() -> Dict[str, ClipMeta]:
    """The 300-clip Nexar set and its labels, from the committed StudyD14b cloud-score trace.

    This is the SAME meta StudyE9b's `load()` builds and the streaming-AP engine is defined on,
    read from the same file, so the AP labels here are the committed ones by construction.
    """
    require(D14B_TRACE, "StudyD14b Nexar score trace (clip set, labels, durations, event times)")
    g: Dict[str, int] = collections.Counter()
    meta: Dict[str, Dict[str, Any]] = {}
    for ln in gzip.open(D14B_TRACE, "rt"):
        r = json.loads(ln)
        clip = r["file_name"]
        if r["model"] == "32BI" and int(r["n"]) == 1:
            g[clip] += 1
        if clip not in meta:
            meta[clip] = dict(label=r["label"], duration_s=float(r["duration_s"]),
                              event_s=(float(r["time_of_event"])
                                       if r["time_of_event"] is not None else None))
    out = {}
    for clip, m in meta.items():
        out[clip] = ClipMeta(clip=clip, label=m["label"], duration_s=m["duration_s"],
                             event_s=m["event_s"], grid_points=int(g[clip]))
    return out


def nexar_instants(duration_s: float,
                   cadence_s: float = NEXAR_INSTANT_CADENCE_S) -> List[float]:
    """Decision instants inside one clip: t = 3.0, 3.5, ... <= duration (StudyCTRL1c cadence)."""
    out, t = [], NEXAR_GRID_T0_S
    while t <= duration_s + 1e-9:
        out.append(round(t, 6))
        t += cadence_s
    return out


# ------------------------------------------------------------------ D2 token accounting
def d2_batch_tokens(n_frames: int, first_batch: bool) -> int:
    """StudyRH4's D2 accounting: 90 tokens per 352x256 image, plus the 31-token header once."""
    return int(n_frames * D2_TOK_PER_IMG + (D2_HEADER_TOK if first_batch else 0))


def d2_frames_in(t_from: float, t_to: float) -> List[float]:
    """D2 frame timestamps in (t_from, t_to]: the fixed 2-s stride from the session start."""
    k0 = int(t_from // D2_STRIDE_S) + 1
    out = []
    t = k0 * D2_STRIDE_S
    while t <= t_to + 1e-9:
        out.append(round(t, 6))
        t += D2_STRIDE_S
    return out


# ================================================================ rulings 2-11 inputs
# Added after the user's rulings on the part-1 open issues (design log D81-D94). Every path below
# is a committed artefact in this repository; nothing is synthesised and nothing is substituted.

SEMBER_MCQ = ROOT / "results/sember/study_h/data/sember_mcq.jsonl"
SEMBER_R1_MANIFEST = ROOT / "results/sember/study_r1/study_r1_inputs_manifest.jsonl.gz"
SEMBER_SPLIT_MODULE = ROOT / "experiments/orchestration/baselines/sember_split.py"

# D87: the device recall comparator. THE EXACT 4B-I x RECENT SET StudyR1 USED, 845 questions at
# 32.78 % (277 / 845), restricted to EVAL by the committed split. Identified by filtering this
# file to model_arm == "4B-I" and state_arm == "RECENT"; the other two cells in the same file are
# 8B-I x RICH (36.21 %) and 4B-T x RICH (30.89 %), so the cell is unambiguous.
DEVICE_RECALL_SET = ROOT / "results/sember/study_o/study_o_q4_trials_fa2.jsonl"
DEVICE_RECALL_SET_SHA256 = ("a847e071696312bcdeabb2b2c9f030dc"
                            "9386b042f53f955f5ba637c360e3b573")
DEVICE_RECALL_N = 845
DEVICE_RECALL_CORRECT = 277

# Per-instant Orin device scores AND per-instant Orin device latency on the dense 0.25-s grid.
ORIN_DENSE_SCORES = ROOT / "results/dashcam/study_orin1/orin1_dense_scores.jsonl.gz"
ORIN_CALIBRATION = ROOT / "results/dashcam/study_orin2/orin2_calibration.json"

# D87: device recall COST = the ORIN2 in-process harness. The server re-send path is an API
# artifact (repo D61) and is not used anywhere in round 1.
ORIN_RECALL_TTFT_S = {11_000: 0.146, 28_000: 0.225}
# D87 amendment 2 / StudyD8: arms whose published mechanism waits for the device's answer.
DEVICE_WAIT_RULE_S = 0.567

# Caveats that must appear in EVERY scorer output header.
SEMBER_JPEG_CAVEAT = (
    "D70: the wire format is JPEG. S-EMBER q88 parity is NOT proven within the pre-registered "
    "+/- 2 pp rule (K3 +0.83 pp [-0.24, +2.01], K1 -0.6 pp with lower bound -2.14, about 6 % of "
    "letters change). S-EMBER cloud accuracy here is the cloud's actual answers on JPEG input."
)
DEVICE_ANSWER_CAVEAT = (
    "D87: robot device answers are the 4B-I x RECENT set of StudyO-Q4 (845 questions, 32.78 %), "
    "restricted to EVAL. They were produced by the 4B on the A6000 / H100, NOT on the Orin. "
    "StudyD15 Part A rejected the H100-for-Orin proxy as an exact numerical stand-in, so these "
    "answers are valid for ordering and first-order value, not as exact device numbers."
)
CACHE_PATH_CAVEAT = (
    "D81: vLLM's prefix-cache path is not output-identical to recompute (StudyORIN3 Part 2: "
    "first-token drift p50 0.22, max 0.45 nats; 39 / 40 answers agree). Robot accuracy is "
    "reported split WARM / COLD from the request log's cache_path."
)
AP_CAVEAT = (
    "D85: dashcam task value is streaming AP over the clip-PLAYS completed in the run, indexed "
    "by play id and paired across arms. It is NOT comparable to the committed 300-clip AP. "
    "D84: repeated clips or sessions across devices are separate plays and are NOT independent "
    "samples."
)


# ------------------------------------------------------------------ S-EMBER EVAL sessions
@dataclass
class Question:
    question_id: str
    t_ask: float                 # session time, the real annotated question_time
    question: str
    options: List[str]
    gold_letter: str
    category: str


@dataclass
class SessionMeta:
    session_id: str              # the S-EMBER video_id
    duration_s: float
    questions: List[Question]


def _session_bounds(video_id: str) -> Tuple[float, float]:
    """`<uid>_start_<s>_end_<e>` encodes its own bounds, so duration needs no file."""
    try:
        head, rest = video_id.split("_start_", 1)
        s, e = rest.split("_end_", 1)
        return float(s), float(e)
    except Exception as exc:
        raise MissingInput(f"cannot read session bounds from video_id {video_id!r}") from exc


def _eval_question_ids() -> set:
    """The committed StudyB-baselines amendment-2 split, computed by its own module."""
    import importlib.util
    require(SEMBER_SPLIT_MODULE, "the committed S-EMBER DEV / EVAL split module")
    spec = importlib.util.spec_from_file_location("live2_sember_split", SEMBER_SPLIT_MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return set(mod.split()["eval_questions"])


# D142 item 1 / D143 ruling A: the LONG-HORIZON robot question set. Robots in a live policy run
# draw ONLY from these questions, whose evidence lies outside the 120 s recent window, and ONLY
# from the EVAL split. The ids come from the COMMITTED definition file, never re-derived here: two
# independently written filters over the same 97 would differ somewhere and nothing would catch it.
LH_REQ_DEFINITION = ROOT / "results/orchestration/live2/lh_req/lh_req_definition.json"

ROBOT_QUESTION_SETS = ("eval", "lh_req")

_LH_REQ: Optional[set] = None


def lh_req_question_ids() -> set:
    """The committed LH-REQ ids, case-folded, intersected with the EVAL split.

    CASE IS THE TRAP HERE and it has caught two sessions. Both id collections are mixed case: the
    split module's eval set is 444 lower and 158 upper, LH-REQ is 63 lower and 34 upper. Folding
    ONE side and calling the split module's plain set membership returns EVAL 43 / DEV 20 with 34
    unmatched, and 34 is exactly the count of upper-case LH-REQ ids, so the wrong answer looks
    plausible. The committed per_split totals are the only thing that catches it, which is why the
    assertion below reads them from the file rather than trusting this function.
    """
    global _LH_REQ
    if _LH_REQ is None:
        require(LH_REQ_DEFINITION, "the committed LH-REQ question-set definition (D142 item 1)")
        d = json.loads(LH_REQ_DEFINITION.read_text())
        allids = {q.lower() for q in d["lh_req_question_ids"]}
        if len(allids) != int(d["n"]):
            raise MissingInput("LH-REQ ids collide under case folding: %d distinct of %d"
                               % (len(allids), int(d["n"])))
        ev = {q.lower() for q in _eval_question_ids()}
        keep = allids & ev
        want = int(d["per_split"]["EVAL"])
        if len(keep) != want:
            raise MissingInput(
                "LH-REQ x EVAL is %d but the committed definition says per_split EVAL = %d. This "
                "is the case-folding control, not a cosmetic check: fold both sides."
                % (len(keep), want))
        _LH_REQ = keep
    return _LH_REQ


_SESSIONS: Optional[Dict[str, SessionMeta]] = None
_LH_REQ_SESSIONS: Optional[Dict[str, SessionMeta]] = None


def eval_sessions() -> Dict[str, SessionMeta]:
    """The 164 S-EMBER EVAL sessions with their REAL annotated question times (D68, D83).

    Questions, options and gold come from `sember_mcq.jsonl`, the only committed file carrying
    all three together. The split is the committed one. Nothing is synthesised: the only
    convention is the committed session convention (order by question_time).
    """
    global _SESSIONS
    if _SESSIONS is None:
        require(SEMBER_MCQ, "S-EMBER MCQ questions, options, gold and question times")
        keep = _eval_question_ids()
        by: Dict[str, List[Question]] = collections.defaultdict(list)
        dur: Dict[str, float] = {}
        for ln in open(SEMBER_MCQ):
            r = json.loads(ln)
            qid = r["question_id"]
            if qid not in keep:
                continue
            vid = r["video_id"]
            if vid not in dur:
                s, e = _session_bounds(vid)
                dur[vid] = e - s
            opts = r["options"]
            if isinstance(opts, str):
                import ast
                opts = ast.literal_eval(opts)
            by[vid].append(Question(question_id=qid, t_ask=float(r["question_time"]),
                                    question=r["question"], options=list(opts),
                                    gold_letter=r["correct_letter"],
                                    category=r.get("question_category", "")))
        out = {}
        for vid, qs in by.items():
            qs.sort(key=lambda q: (q.t_ask, q.question_id))
            out[vid] = SessionMeta(session_id=vid, duration_s=dur[vid], questions=qs)
        if not out:
            raise MissingInput("the EVAL split selected no S-EMBER question")
        _SESSIONS = out
    return _SESSIONS


def lh_req_sessions() -> Dict[str, SessionMeta]:
    """EVAL sessions carrying at least one LH-REQ question, with ONLY those questions kept.

    Sessions with no LH-REQ question are dropped from the pool entirely. Keeping them would have a
    robot play a session that can never ask anything, which does not change the question count but
    does change how many sessions the chain gets through, so the two are not interchangeable.

    Session durations, question times, options and gold are untouched: this is a filter on the
    question list, not a new workload.
    """
    global _LH_REQ_SESSIONS
    if _LH_REQ_SESSIONS is None:
        keep = lh_req_question_ids()
        out: Dict[str, SessionMeta] = {}
        for vid, sm in eval_sessions().items():
            qs = [q for q in sm.questions if q.question_id.lower() in keep]
            if qs:
                out[vid] = SessionMeta(session_id=vid, duration_s=sm.duration_s, questions=qs)
        n = sum(len(s.questions) for s in out.values())
        if n != len(keep):
            raise MissingInput(
                "the LH-REQ session filter kept %d questions but %d ids were selected, so some id "
                "does not appear in any EVAL session" % (n, len(keep)))
        _LH_REQ_SESSIONS = out
    return _LH_REQ_SESSIONS


def robot_sessions(question_set: str = "eval") -> Dict[str, SessionMeta]:
    """The robot session pool for a named question set. One entry point, so a caller cannot pick
    the pool and the question filter independently and get a mismatched pair."""
    if question_set not in ROBOT_QUESTION_SETS:
        raise ValueError("question_set %r not in %r" % (question_set, ROBOT_QUESTION_SETS))
    return eval_sessions() if question_set == "eval" else lh_req_sessions()


# ------------------------------------------------------------------ device answers (D87)
_DEV_RECALL: Optional[Dict[str, Dict[str, Any]]] = None


SS1_DIR = ROOT / "results" / "casestudy" / "study_ss1"
# D136 item 1: VizWiz FIRST, EgoThink second. The order is the brief's and is load-bearing, since
# a fleet smaller than the VizWiz pool never reaches EgoThink at all.
SS1_SOURCES = (("vizwiz", SS1_DIR / "vizwiz_val_manifest.jsonl",
                SS1_DIR / "vizwiz_val_device.json", 4319),
               ("egothink", SS1_DIR / "egothink_manifest.jsonl",
                SS1_DIR / "egothink_device.json", 700))
_SS1 = None


def ss1_questions(verify: bool = True) -> List[Dict[str, Any]]:
    """The StudySS1 single-shot pool, VizWiz then EgoThink, each with its committed device answer.

    PROVENANCE IS UNCONFIRMED AND THAT IS RECORDED RATHER THAN ASSUMED. These five artifacts carry
    NO `_provenance` block, which CLAUDE.md requires. They record `tier=device` and
    `model=qwen3vl4b` with `endpoint: http://127.0.0.1:8000/v1`, which is localhost on whichever
    machine ran them. So the brief's "Orin 4B answer" cannot be confirmed from the file, and Orin
    against an A6000 proxy is a DIFFERENT DEVICE TIER. Every row therefore carries
    `device_host="unconfirmed"`, and anything derived from it must say so.

    `verify=True` re-derives each file's own committed `n` before use, so a wrong or truncated file
    stops the run instead of being scored.
    """
    global _SS1
    if _SS1 is not None:
        return _SS1
    out: List[Dict[str, Any]] = []
    for name, man, dev, n_expect in SS1_SOURCES:
        require(man, f"StudySS1 {name} manifest (D136)")
        require(dev, f"StudySS1 {name} device answers (D136)")
        d = json.load(open(dev))
        if verify and int(d.get("n", -1)) != n_expect:
            raise MissingInput(
                f"StudySS1 {name} device file does not reproduce its committed n: got "
                f"{d.get('n')!r}, expected {n_expect}")
        ans = {r["qid"]: r for r in d.get("rows", [])}
        for ln in open(man):
            r = json.loads(ln)
            a = ans.get(r["qid"])
            if a is None:
                continue
            out.append(dict(qid=r["qid"], dataset=name, question=r["question"],
                            image=r.get("image"), image_sha16=r.get("image_sha16"),
                            references=list(r.get("references") or []),
                            prompt_tokens=int(a.get("prompt_tokens") or 1),
                            # SUBSTITUTION, checked rather than accepted. StudySS1 records no
                            # per-image byte count. The images themselves would be measurable, and
                            # the H100 verified staging (700 EgoThink hash-matching, 4,319 VizWiz
                            # present), but they live at /dev/shm/ss1_data per
                            # `ss1_build_manifests.py`, which is MACHINE-LOCAL tmpfs and is empty
                            # on this host, so `stat` is not available from here.
                            #
                            # So the committed S-EMBER D2 median stands in. The direction of error
                            # is UNKNOWN and that matters: S-EMBER D2 frames are 352x256 JPEG q88
                            # while VizWiz and EgoThink come from entirely different sources at
                            # unknown resolutions, so assistive uplink cost may be over- or
                            # understated. Measuring on a host where the staging is live would
                            # REMOVE this substitution rather than document it.
                            image_bytes=int(round(E10A_SEMBER_Q88_D2_MEDIAN_B)),
                            device_answer=a.get("answer"),
                            device_score=(a.get("score") or {}),
                            device_model=d.get("model"), device_tier=d.get("tier"),
                            device_host="unconfirmed"))
    _SS1 = out
    return out


# ---------------------------------------------------------------- StudySS2 single-shot pool (D143)
SS2_DIR = ROOT / "results" / "casestudy" / "study_ss2"
SS2_SPLIT = SS2_DIR / "ss2_dev_eval_split.json"
# RefSpatial FIRST, RealWorldQA second. The order is load-bearing in the same way SS1's was: a
# fleet small enough never to exhaust the first dataset never reaches the second.
SS2_SOURCES = (("refspatial", SS2_DIR / "refspatial_manifest.jsonl",
                SS2_DIR / "refspatial_device.json", 277),
               ("realworldqa", SS2_DIR / "realworldqa_manifest.jsonl",
                SS2_DIR / "realworldqa_device.json", 765))
SS_QUESTION_SETS = ("ss1", "ss2")
_SS2 = None
_SS2_SPLIT = None


def ss2_split() -> Dict[str, Any]:
    """The committed seeded 30 / 70 DEV / EVAL split, READ not re-derived (D143 ruling A)."""
    global _SS2_SPLIT
    if _SS2_SPLIT is None:
        require(SS2_SPLIT, "the committed StudySS2 DEV / EVAL split "
                           "(experiments/casestudy/ss2_make_split.py writes it)")
        d = json.loads(SS2_SPLIT.read_text())
        for name, blk in d["per_dataset"].items():
            dev, ev = set(blk["dev_qids"]), set(blk["eval_qids"])
            if dev & ev:
                raise MissingInput("SS2 split overlaps on %s: %d qids in both parts"
                                   % (name, len(dev & ev)))
            if len(dev) + len(ev) != int(blk["n"]):
                raise MissingInput("SS2 split for %s covers %d of %d questions"
                                   % (name, len(dev) + len(ev), blk["n"]))
        _SS2_SPLIT = d
    return _SS2_SPLIT


def ss2_questions(part: str = "eval", verify: bool = True) -> List[Dict[str, Any]]:
    """The StudySS2 single-shot pool, RefSpatial then RealWorldQA, restricted to one split part.

    D143 ruling A: SS devices draw from the EVAL part; the SS quality table is fitted on DEV. The
    default is therefore "eval", the part a run is allowed to draw from.

    PROVENANCE IS PRESENT HERE, unlike StudySS1. Both device files carry a `_provenance` block
    naming `device: jetson_orin` with the script, commit and timestamp, so the device tier is read
    from the file rather than taken on anyone's word. The caching string in those files is a
    DECLARATION and is NOT trusted: StudySS2's within-image test showed both tiers served repeated
    images warm, so `device_cold_per_image` below records what was measured, not what was claimed.

    `verify=True` re-derives each file's own committed `n` before use.
    """
    global _SS2
    if part not in ("dev", "eval"):
        raise ValueError("part %r must be 'dev' or 'eval'" % (part,))
    if _SS2 is None:
        sp = ss2_split()["per_dataset"]
        out: Dict[str, List[Dict[str, Any]]] = dict(dev=[], eval=[])
        for name, man, dev_f, n_expect in SS2_SOURCES:
            require(man, f"StudySS2 {name} manifest")
            require(dev_f, f"StudySS2 {name} device answers")
            d = json.loads(dev_f.read_text())
            if verify and int(d.get("n", -1)) != n_expect:
                raise MissingInput(
                    f"StudySS2 {name} device file does not reproduce its committed n: got "
                    f"{d.get('n')!r}, expected {n_expect}")
            prov = d.get("_provenance") or {}
            ans = {r["qid"]: r for r in d.get("rows", []) if "error" not in r}
            which = {q: "dev" for q in sp[name]["dev_qids"]}
            which.update({q: "eval" for q in sp[name]["eval_qids"]})
            for ln in man.read_text().splitlines():
                if not ln.strip():
                    continue
                r = json.loads(ln)
                a = ans.get(r["qid"])
                if a is None:
                    continue
                w = which.get(r["qid"])
                if w is None:
                    raise MissingInput("StudySS2 question %r is in no split part" % r["qid"])
                out[w].append(dict(
                    qid=r["qid"], dataset=name,
                    question=r.get("question") or r.get("prompt_text"),
                    image=r.get("image"), image_sha16=r.get("image_sha16"),
                    width=int(r["width"]), height=int(r["height"]),
                    references=list(r.get("references") or []),
                    subset=str(r[sp[name]["subset_field"]]),
                    prompt_tokens=int(a.get("prompt_tokens") or 1),
                    # SAME SUBSTITUTION AS SS1, but its direction is now KNOWN rather than unknown.
                    # StudySS2 records no per-image byte count either, so the committed S-EMBER D2
                    # median stands in for uplink bytes. SS1 had to call the direction of error
                    # unknown because VizWiz and EgoThink resolutions were not held. SS2's
                    # manifests carry width and height on every row: areas run 196,608 to
                    # 2,158,080 px against S-EMBER D2's 352 x 256 = 90,112 px, so every SS2 image
                    # is 2.2x to 24x larger in area and the substitution almost certainly
                    # UNDERSTATES assistive uplink cost. Measuring the staged files would remove
                    # it rather than bound it.
                    image_bytes=int(round(E10A_SEMBER_Q88_D2_MEDIAN_B)),
                    image_area_px=int(r["width"]) * int(r["height"]),
                    device_answer=a.get("answer"),
                    device_score=(a.get("score") or {}),
                    device_model=d.get("model"), device_tier=d.get("tier"),
                    device_host=prov.get("device") or "unconfirmed",
                    device_cold_per_image=(
                        "NOT cold wherever images repeat. StudySS2 measured, within-image on the "
                        "61 shared RefSpatial images with prompt tokens held at 335 against 337, "
                        "that later occurrences were 27.5 percent faster on the device and 33.4 "
                        "percent on the cloud. cache_salt isolates the TEXT prefix cache only; "
                        "the multimodal cache is keyed by image CONTENT. In a live2 run the D84 "
                        "per-(device, opportunity) mm uuid REPLACES that content key, so the live "
                        "harness does not inherit this and the committed SS2 TTFT numbers are not "
                        "the live condition."),
                    split_part=w))
        for part_name in ("dev", "eval"):
            out[part_name].sort(key=lambda q: (SS2_ORDER[q["dataset"]], q["qid"]))
        _SS2 = out
    return _SS2[part]


SS2_ORDER = {name: i for i, (name, _m, _d, _n) in enumerate(SS2_SOURCES)}


def ss_questions(question_set: str = "ss1", part: str = "eval") -> List[Dict[str, Any]]:
    """One entry point for the single-shot pool, so a caller cannot combine a dataset family with
    the wrong split part. "ss1" is the committed default and takes no split (StudySS1 has none)."""
    if question_set not in SS_QUESTION_SETS:
        raise ValueError("question_set %r not in %r" % (question_set, SS_QUESTION_SETS))
    return ss1_questions() if question_set == "ss1" else ss2_questions(part)


def device_recall_answers(verify: bool = True) -> Dict[str, Dict[str, Any]]:
    """D87's device comparator, restricted to EVAL. question_id -> {pred, correct, gold}.

    `verify=True` re-derives the committed 845 / 32.78 % headline from the file before the EVAL
    restriction, so a wrong file or a wrong cell filter stops the run instead of being scored.
    """
    global _DEV_RECALL
    if _DEV_RECALL is None:
        require(DEVICE_RECALL_SET, "D87 device recall answer set (StudyO-Q4 4B-I x RECENT)")
        cell = []
        for ln in open(DEVICE_RECALL_SET):
            r = json.loads(ln)
            if r.get("model_arm") == "4B-I" and r.get("state_arm") == "RECENT":
                cell.append(r)
        if verify:
            got_n, got_c = len(cell), sum(1 for r in cell if r["correct"])
            if (got_n, got_c) != (DEVICE_RECALL_N, DEVICE_RECALL_CORRECT):
                raise MissingInput(
                    f"D87 device set does not reproduce its committed headline: got "
                    f"{got_c}/{got_n} = {100.0 * got_c / max(got_n, 1):.2f} %, expected "
                    f"{DEVICE_RECALL_CORRECT}/{DEVICE_RECALL_N} = 32.78 %")
        keep = _eval_question_ids()
        out = {r["question_id"]: dict(pred=r["pred"], correct=bool(r["correct"]),
                                      gold=r["correct_letter"],
                                      evidence_covered=r.get("evidence_covered"),
                                      video_id=r["video_id"])
               for r in cell if r["question_id"] in keep}
        if not out:
            raise MissingInput("the EVAL restriction of the D87 device set is empty")
        _DEV_RECALL = out
    return _DEV_RECALL


def device_recall_latency_s(history_tokens: float) -> float:
    """D87's ORIN2 in-process harness cost, two committed points, linear between them.

    DERIVED: the committed values are 0.146 s at 11k and 0.225 s at 28k tokens (StudyORIN2-stack,
    in-process libllama + libmtmd). Round 1 needs a cost at other history sizes, so this
    interpolates linearly and CLAMPS outside the measured range rather than extrapolating. The
    interpolation is a derived rule, not a committed measurement, and the report says so.
    """
    (t0, v0), (t1, v1) = sorted(ORIN_RECALL_TTFT_S.items())
    if history_tokens <= t0:
        return v0
    if history_tokens >= t1:
        return v1
    return v0 + (v1 - v0) * (history_tokens - t0) / (t1 - t0)


# ------------------------------------------------------------------ Orin dense scores
_ORIN_DENSE: Optional[Dict[Tuple[str, float], Dict[str, float]]] = None


def orin_dense_scores() -> Dict[Tuple[str, float], Dict[str, float]]:
    """(file_name, t) -> per-instant Orin score and per-instant Orin latency (42,014 rows).

    Keyed on `file_name` ("00005.mp4"), which is the key `nexar_clip_meta` and StudyE9b's AP
    engine both use; the row's own `clip` field is the stem without the extension.

    The device answer AND its latency come from the same row, so the emulator never uses a
    constant where a measured per-instant value exists.
    """
    global _ORIN_DENSE
    if _ORIN_DENSE is None:
        require(ORIN_DENSE_SCORES, "StudyORIN1 dense per-instant Orin scores and latency")
        out = {}
        for ln in gzip.open(ORIN_DENSE_SCORES, "rt"):
            r = json.loads(ln)
            out[(r["file_name"], round(float(r["t"]), 6))] = dict(
                score=float(r["score"]), p_yes=float(r["p_yes"]),
                ttft_s=float(r["ttft_s"]), total_s=float(r["total_s"]))
        _ORIN_DENSE = out
    return _ORIN_DENSE


# ------------------------------------------------------------------ calibration (D86)
def calibration(path: Path = ORIN_CALIBRATION) -> Dict[str, Any]:
    """Load a per-tier calibration map file and LABEL it (D86, ruling 10/11).

    Maps are INPUT files. A map is FINAL only if the file itself declares
    `"label": "FINAL"` AND `"fit_sample": "dense"`; everything else, including the committed
    `orin2_calibration.json`, is INTERIM. The committed file is not modified to say so: the
    label is derived here, conservatively, so a missing declaration can never be read as FINAL.
    """
    require(path, "per-tier calibration map (D57, D86)")
    d = json.loads(Path(path).read_text())
    label = "FINAL" if (d.get("label") == "FINAL" and d.get("fit_sample") == "dense") \
        else "INTERIM"
    maps = {"device_4b_orin": dict(a=float(d["a"]), b=float(d["b"]))}
    for k, v in (d.get("compare") or {}).items():
        maps[k] = dict(a=float(v["a"]), b=float(v["b"]))
    # D105: a dense refit is Platt-fitted with 5-fold CROSS-FITTING BY CLIP (D6), and each clip
    # is scored with the map from the folds that EXCLUDE it. `folds.maps[k]` is therefore the map
    # fitted with fold k held out, and a clip assigned to fold k is scored with it. The fold
    # assignment comes from the FILE: the scorer never invents one, and never falls back to the
    # pooled map for a clip the file does not place in a fold.
    folds = None
    fo = d.get("folds")
    if isinstance(fo, dict):
        fm: Dict[str, Dict[str, Dict[str, float]]] = {}
        for k, mv in (fo.get("maps") or {}).items():
            fm[str(k)] = {mk: dict(a=float(v["a"]), b=float(v["b"])) for mk, v in mv.items()}
        folds = dict(n_folds=int(fo.get("n_folds") or len(fm)),
                     by=str(fo.get("by") or "clip"),
                     assignment={str(c): str(f) for c, f in
                                 (fo.get("assignment") or {}).items()},
                     maps=fm,
                     note=("D105: maps[k] is fitted with fold k HELD OUT, so a clip in fold k "
                           "is scored out-of-fold with maps[k]."))
    return dict(path=str(path), sha256=sha256_of(Path(path)), label=label, maps=maps,
                folds=folds, fit_split=d.get("fit_split"),
                note=("D86: fitted on an event-anchored sample, not a dense trajectory; the "
                      "D3-fitted device slope is 3.007x steeper than a D14b-DEV dense fit "
                      "(+0.114603 vs +0.038113). The dense refit for both tiers is an H100 task."
                      if label == "INTERIM" else None))


def calibrate(score: float, m: Dict[str, float]) -> float:
    """D57 / StudyORIN2: log_odds = a * log(p_yes) + b, with `score` already log p_yes."""
    return m["a"] * score + m["b"]
