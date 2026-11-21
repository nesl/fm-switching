#!/usr/bin/env python3
"""Confirm the three policy-v5 engine actions on the DEPLOYMENT stack. RUN ONLY, no build.

StudyV5-ENGINE, the h100nvl confirmation leg (research/EXPERIMENTS.md row StudyV5-ENGINE,
USER-AUTHORIZED 2026-11-20). This script is meant to be run BY HAND on the H100 at a run
boundary, against the already-running round-1 32B server. It installs nothing, compiles nothing,
edits nothing and starts no server. Every parameter comes from a committed file or a CLI flag,
and anything it cannot establish it reports as NOT ESTABLISHED with the reason.

EXPECTED WALL CLOCK: 6 to 10 minutes with the defaults; hard-capped by --duration-budget-s
(default 900 s = 15 min). The cap is enforced BEFORE each phase and before each repetition, so a
phase that does not fit is recorded as NOT ATTEMPTED (budget) rather than overrunning the break.

THE THREE MEASUREMENTS, as the user fixed them.

  M1  WARM-AHEAD RAISES CACHED TOKENS AT QUESTION TIME. One session's uploaded frames are
      prefilled ahead of any question as a chain of small prefill-only pieces (the committed
      `engine_actions.WARM_AHEAD_SLICE_TOKENS` discipline), then the committed recall question is
      sent and the engine's own `prompt_tokens_details.cached_tokens` is read. The comparison arm
      is the SAME question over the SAME frames on a different device, with no warm-ahead, which
      D84's per-device `cache_salt` and per-(device, frame) mm uuid make a genuinely cold prefix
      chain. Cached tokens and TTFT are reported for both arms.

  M2  A TOUCHED HISTORY SURVIVES WHERE AN UNTOUCHED ONE IS EVICTED. Two histories are built, one
      is touched, and enough other traffic is driven to push exactly one history past the
      engine's eviction frontier. The frontier is MEASURED on the live server first (a sentinel
      ladder), not assumed from the committed pool sizes, because under native offloading it is
      not known a priori whether the GPU and host tiers add or whether write-through makes the
      host window dominate. vLLM cannot pin KV, so this is a probability, not a promise: the
      result is reported as COUNTS over repetitions, with a control condition that touches
      NOTHING and therefore predicts the OPPOSITE winner.

  M3  RELOAD-FROM-HOST IS FASTER THAN A COLD REBUILD. Across 56 committed 16-device cells the
      coordinator's `believed_tier` is NEVER `host` (reports/study_engine_actions.md section 2),
      so this action's trigger state has never been observed in our harness. This script
      therefore CREATES the host-resident condition directly on the engine and VERIFIES it before
      timing anything, using the committed StudyENG1c residency classifier over the server's own
      `prompt_tokens_by_source` / `external_prefix_cache_*` counters. If host residency cannot be
      verified, M3 is reported NOT ESTABLISHED and no timing is called a reload.

WHAT THIS SCRIPT DOES NOT DO, and must not be read as doing.

  * It does not measure accuracy and it reads no answer text as a score.
  * It does not exercise the HARNESS wiring of these actions. `coordinator._enact`'s
    `KEEP_GPU_WARM` branch (coordinator.py:482) sets `SessionRec.desired_tier` and emits NO
    request, so a harness touch cannot move the engine's own eviction order. M2 confirms the
    ENGINE PROPERTY the policy's touch lever depends on; it does not confirm that the lever as
    currently wired reaches the engine. That gap is reported in the result JSON under
    `caveats.touch_wiring` and must travel with any citation of M2.
  * It is not a sweep and produces no policy comparison.

CACHING IS A METHODOLOGICAL PARAMETER (CLAUDE.md). The round-1 server runs
`--enable-prefix-caching --enable-prompt-tokens-details --mm-processor-cache-gb 128
--kv-offloading-backend native --kv-offloading-size 27`. Prefix caching is therefore ON for every
request this script sends, and the script never compares a warm number to a cold one without
labelling both: every measured row carries a `cache` block stating the condition (WARM or COLD),
what was cached before it was sent, and whether a repeat of it could be served from cache. The
preflight runs a prefix-cache POSITIVE CONTROL (a same-salt repeat must report reuse, a
fresh-salt repeat must not) before any measurement, because a check that cannot fail is not a
check (CLAUDE.md consistency check 7).

USAGE on the H100, at a run boundary, with the round-1 32B server already serving:

    ~/.venvs/fm-switching-vllm/bin/python \
        experiments/orchestration/live2/confirm_engine_actions_32b.py

and to validate the script's own logic with no GPU and no 32B anywhere (this is what flash ran):

    python3 experiments/orchestration/live/fake_server.py --port 8077 &
    python3 experiments/orchestration/live2/confirm_engine_actions_32b.py \
        --dry --base-url http://127.0.0.1:8077 --served-model fake-32BI

A --dry run MUST report all three measurements NOT ESTABLISHED, because the CPU stub reports no
`cached_tokens`, models no prefix cache and exposes no offload counters. If a dry run ever
reports a pass, this script is fabricating one.
"""
from __future__ import annotations

import argparse
import base64
import json
import random
import re
import statistics
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for _p in (HERE, REPO / "experiments/orchestration/live",
           REPO / "experiments/orchestration/live2/fleet",
           REPO / "experiments/orchestration/baselines",
           REPO / "experiments/orchestration/sim",
           REPO / "experiments/orchestration", REPO / "experiments/lib"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import bodies as B                                              # noqa: E402
import cachekeys as CK                                          # noqa: E402
import engine_actions as EA                                     # noqa: E402
from backend import (Live2Backend, Live2Submission,              # noqa: E402
                     cached_tokens_of, output_tokens_of, prompt_tokens_of)

SCRIPT = "confirm_engine_actions_32b.py"
VERSION = "confirm-engine-actions-32b-1.0"

# ---------------------------------------------------------------------------- committed constants
# Every number here is READ OFF a committed artefact and the citation is the point of the comment.
GPU_POOL_TOKENS = 62_944          # StudyENG1/ENG1b/ENG1c KV-HOST GPU pool; also checked at every
                                  # round-1 server start (results/.../live2_pre_server.json
                                  # "kv_cache_tokens"); experiments/cost/study_eng1c_hostfull.py
                                  # GPU_POOL
TOK_PER_GIB = 4_096              # ENG1c: one host chunk = one 16-token GPU block = 4 MiB, so a
                                  # C GiB host cap holds C * 4096 tokens
HOST_CAP_GIB = 27                # the deployment stack's --kv-offloading-size
HOST_CAP_TOKENS = HOST_CAP_GIB * TOK_PER_GIB            # 110,592
BLOCK_TOKENS = 16                # vLLM block size (ENG1c BLK)
COLD_OK_CACHED_MAX = BLOCK_TOKENS    # ENG1c build gate: <= 16 cached tokens on a fresh namespace
                                     # counts as cold (study_eng1c_hostfull.py:362 `cold_ok`)
GPU_CLASSIFY_FRAC = 0.5          # ENG1c `classify`: local >= 0.5 * prompt_tokens means GPU
HOST_CLASSIFY_FRAC = 0.9         # ENG1c `classify`: external >= 0.9 * (n - local) means host
PARTIAL_HOST_MIN = 64            # ENG1c `classify`: external > 64 means partial_host
D2_TOK_PER_IMG = 90             # StudyRH4, via fleet/data_sources.D2_TOK_PER_IMG
D2_HEADER_TOK = 31              # StudyRH4, the "D2 history" header
S_HIST_TOKENS = 11_184          # D56 nominal history, ENG1c S_HIST
HEADER_TEXT = "D2 history"      # coordinator.py:73, the committed build header
DEFAULT_BASE_URL = "http://127.0.0.1:8031"   # round-1 server --port 8031, --host 127.0.0.1
DEFAULT_SERVED_MODEL = "32BI"                # round-1 server --served-model-name 32BI
MAX_MODEL_LEN = 32_768                       # round-1 server --max-model-len
D2_STORE = Path("~/data/live2/jpeg/sember_d2_q88").expanduser()
COMBINED_MANIFEST = Path("~/data/live2/jpeg/combined_manifest.jsonl").expanduser()

# The vLLM metric families this script reads, and the two residency channels it can use. Names
# come from experiments/cost/study_eng1_steptime.py MET_KEEP and study_eng1c_hostfull.py `src`.
MET_KEEP = ("prefix_cache_", "external_prefix_cache_", "prompt_tokens_by_source",
            "prompt_tokens_cached", "kv_cache_usage", "gpu_cache_usage", "kv_block_",
            "num_requests_", "mm_cache_", "offload", "connector", "kv_transfer")
SRC_LOCAL = "prompt_tokens_by_source_total|local_cache_hit"
SRC_EXTERNAL = "prompt_tokens_by_source_total|external_kv_transfer"
SRC_COMPUTE = "prompt_tokens_by_source_total|local_compute"
EXT_HITS = "external_prefix_cache_hits_total"
EXT_QUERIES = "external_prefix_cache_queries_total"

# A minimal valid JPEG, DRY MODE ONLY. It exists so --dry can exercise the real body builder, the
# real uuid conventions and the real wire form on a box that holds no round-1 frames. The script
# refuses to use it without --dry, so it can never reach a real engine.
_DRY_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
    "HBwcJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPDI0NP/AABEIABAAEAMBIgACEQEDEQH/xAAfAAAB"
    "BQEBAQEBAQAAAAAAAAABAgMEBQYHCAkKC//EALUQAAIBAwMCBAMFBQQEAAABfQECAwAEEQUSITFB"
    "BhNRYQcicRQygZGhCCNCscEVUtHwJDNicoIJChYXGBkaJSYnKCkqNDU2Nzg5OkNERUZHSElKU1RV"
    "VldYWVpjZGVmZ2hpanN0dXZ3eHl6g4SFhoeIiYqSk5SVlpeYmZqio6Slpqeoqaqys7S1tre4ubrC"
    "w8TFxsfIycrS09TV1tfY2drh4uPk5ebn6Onq8fLz9PX29/j5+v/aAAwDAQACEQMRAD8A9/ooooA/"
    "/9k=")


# The CPU stub's time compression. 1.0 everywhere on a real server (bodies.py puts it on the
# wire as the stub hint `fm_time_scale`, which `backend.Live2Backend(strip_hints=True)` removes
# before a real request leaves); --dry lowers it so the stub's committed service-time draws do not
# make a logic validation take as long as a real run.
_TIME_SCALE = 1.0


def _bb(**kw: Any) -> Dict[str, Any]:
    """`bodies.build_body`, with the stub's time scale attached. The committed builder is the only
    thing that constructs a body in this script."""
    return B.build_body(time_scale=_TIME_SCALE, **kw)


class Stop(RuntimeError):
    """A loud, explained stop. Never swallowed, never guessed around."""


# ---------------------------------------------------------------------------- budget
class Budget:
    """The break's wall clock. Checked before each phase and each repetition."""

    def __init__(self, seconds: float) -> None:
        self.limit = float(seconds)
        self.t0 = time.time()
        self.notes: List[str] = []

    @property
    def spent(self) -> float:
        return time.time() - self.t0

    @property
    def left(self) -> float:
        return self.limit - self.spent

    def have(self, need_s: float, what: str) -> bool:
        ok = self.left >= float(need_s)
        if not ok:
            self.notes.append("skipped %s: %.0f s left, %.0f s needed" % (what, self.left, need_s))
        return ok


# ---------------------------------------------------------------------------- the engine client
def _flatten_metrics(txt: str) -> Dict[str, float]:
    """vLLM's Prometheus text, flattened exactly as study_eng1_steptime.metrics flattens it:
    `<name without the vllm: prefix>` plus `|<source label>` when the series carries one."""
    out: Dict[str, float] = {}
    for line in txt.splitlines():
        if line.startswith("#") or not line.startswith("vllm:"):
            continue
        name, _, val = line.rpartition(" ")
        base = name.split("{")[0][5:]
        if not any(k in base for k in MET_KEEP) or base.endswith("_bucket"):
            continue
        lab = ""
        m = re.search(r'source="([^"]+)"', name)
        if m:
            lab = "|" + m.group(1)
        try:
            out[base + lab] = out.get(base + lab, 0.0) + float(val)
        except ValueError:
            pass
    return out


def mdelta(m0: Dict[str, float], m1: Dict[str, float]) -> Dict[str, float]:
    return {k: round(m1[k] - m0.get(k, 0.0), 6) for k in m1
            if abs(m1[k] - m0.get(k, 0.0)) > 0}


def classify_residency(local: float, external: float, prompt_tokens: Optional[int]) -> Optional[str]:
    """StudyENG1c's own residency classifier (experiments/cost/study_eng1c_hostfull.py:404-414),
    re-implemented here rather than imported because importing that module pulls in the whole
    ENG1 server harness. The thresholds are copied, not chosen."""
    if not prompt_tokens or prompt_tokens <= 0:
        return None
    n = float(prompt_tokens)
    if local >= GPU_CLASSIFY_FRAC * n:
        return "gpu"
    if external >= HOST_CLASSIFY_FRAC * (n - local) and external > 0:
        return "host"
    if external > PARTIAL_HOST_MIN:
        return "partial_host"
    return "cold"


class Engine:
    """The round-1 server, driven one request at a time through the committed live2 client."""

    def __init__(self, base_url: str, served_model: str, dry: bool) -> None:
        self.base_url = base_url.rstrip("/")
        self.served_model = served_model
        self.dry = bool(dry)
        # strip_hints=True on a real server: the fm_* stub hints must not reach vLLM.
        self.bk = Live2Backend(self.base_url, workers=1, model=served_model,
                               strip_hints=not dry, record_bodies=True)
        self.rows: List[Dict[str, Any]] = []
        # The cache keys per request, kept out of the result rows because a row would then carry
        # 124 uuids. The D84 check reads these.
        self.keys: List[Dict[str, Any]] = []
        self.n_requests = 0
        self.metrics_available = False

    # ---- plumbing
    def get(self, path: str, timeout: float = 20.0) -> str:
        req = urllib.request.Request(self.base_url + path)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode(errors="replace")

    def metrics(self) -> Dict[str, float]:
        if not self.metrics_available:
            return {}
        try:
            return _flatten_metrics(self.get("/metrics"))
        except Exception as e:                                           # noqa: BLE001
            self.rows.append(dict(role="metrics_error", error=repr(e)))
            return {}

    def models(self) -> Dict[str, Any]:
        return json.loads(self.get("/v1/models"))

    # ---- the one request primitive
    def send(self, body: Dict[str, Any], *, role: str, phase: str,
             cache: Dict[str, Any], with_metrics: bool = False,
             extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send one body, record one row. `cache` is the methodological label and is MANDATORY."""
        meta = body["_live2"]
        self.n_requests += 1
        rid = "c32b-%04d" % self.n_requests
        sub = Live2Submission(request_id=rid, decision_id=None, kind=meta["kind"],
                              device_id=meta["device_id"], session_id=meta["session_id"],
                              opportunity_id=None, body=body,
                              est_tokens=int(body.get("fm_tokens") or 0), sent_s=time.time(),
                              cache_salt=body.get("cache_salt", ""),
                              mm_uuids=list(meta["mm_uuids"]))
        self.keys.append(dict(role=role, phase=phase, device_id=meta["device_id"],
                              salt=body.get("cache_salt", ""),
                              mm_uuids=list(meta["mm_uuids"])))
        m0 = self.metrics() if with_metrics else {}
        res = self.bk.post_live2(sub)
        usage = res.get("usage") or {}
        d: Dict[str, float] = {}
        if with_metrics:
            time.sleep(0.15)        # ENG1c's own settle before reading the counter delta
            d = mdelta(m0, self.metrics())
        row = dict(phase=phase, role=role, request_id=rid, kind=meta["kind"],
                   device_id=meta["device_id"], session_id=meta["session_id"],
                   n_frames=meta["n_frames"], n_new_frames=meta["n_new_frames"],
                   cache_salt=body.get("cache_salt"),
                   http_status=res.get("http_status"), error=res.get("error"),
                   ttft_s=res.get("ttft_s"), total_s=res.get("total_s"),
                   prompt_tokens=prompt_tokens_of(usage),
                   cached_tokens=cached_tokens_of(usage),
                   completion_tokens=output_tokens_of(usage),
                   external_cached_tokens=EA.external_cached_tokens_of(usage),
                   usage_keys=sorted(usage.keys()) if usage else [],
                   m_local=d.get(SRC_LOCAL), m_external=d.get(SRC_EXTERNAL),
                   m_compute=d.get(SRC_COMPUTE),
                   m_ext_hits=d.get(EXT_HITS), m_ext_queries=d.get(EXT_QUERIES),
                   metrics_delta=(d or None), cache=dict(cache))
        row["residency_class"] = classify_residency(row["m_local"] or 0.0,
                                                    row["m_external"] or 0.0,
                                                    row["prompt_tokens"])
        if extra:
            row.update(extra)
        self.rows.append(row)
        if res.get("error") or (row["http_status"] not in (None, 200)):
            raise Stop("request %s (%s/%s) failed: HTTP %s %s" %
                       (rid, phase, role, row["http_status"], res.get("error")))
        return row


# ---------------------------------------------------------------------------- frames and sessions
def pick_questions(n_frames: int) -> List[Dict[str, Any]]:
    """The committed S-EMBER EVAL questions this confirmation may ask, in a deterministic order.

    Read out of the committed split, never invented. One candidate per EVAL session, its LAST
    question, because that is the question with the most history behind it: at the committed D2
    stride of 2 s, `n_frames` frames need 2 * n_frames seconds of session before the question, and
    138 of the 164 EVAL sessions clear that at their last question against 5 at their first. The
    candidates are returned in sorted-session order and the caller takes the first whose frames
    actually resolve on this host, so one absent frame costs a candidate rather than the run.
    """
    import data_sources as DS
    sessions = DS.eval_sessions()
    if not sessions:
        raise Stop("fleet/data_sources.eval_sessions() returned nothing; the committed EVAL "
                   "split is required and nothing is substituted")
    need_s = 2.0 * int(n_frames)
    out: List[Dict[str, Any]] = []
    for sid in sorted(sessions):
        qs = sorted(sessions[sid].questions, key=lambda q: float(q.t_ask))
        if not qs:
            continue
        q = qs[-1]
        out.append(dict(session_id=sid, question_id=q.question_id, t_ask=float(q.t_ask),
                        question=q.question, options=list(q.options), category=q.category,
                        enough_history=bool(float(q.t_ask) >= need_s),
                        source="fleet/data_sources.eval_sessions(), last question of this EVAL "
                               "session"))
    out.sort(key=lambda c: (not c["enough_history"],))
    if not out:
        raise Stop("no EVAL session carries a question; nothing is substituted")
    return out


def _manifest_paths(manifest: Path) -> Dict[str, Path]:
    out: Dict[str, Path] = {}
    for ln in open(manifest):
        ln = ln.strip()
        if not ln:
            continue
        r = json.loads(ln)
        ref = r.get("frame_ref")
        p = r.get("path") or r.get("file")
        if ref and p:
            out[str(ref)] = Path(str(p)).expanduser()
    return out


def resolve_frames(session_id: str, t_ask: float, n_frames: int, store: Path,
                   manifest: Optional[Path]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """The last `n_frames` committed D2 frames of this session at or before its question.

    The frame_ref is the wire form `fleet/trace.py` emits (`<session>|f<ffffff.ff>`, D2 stride
    2 s, StudyRH4) and the stored file name is `encode_jpeg.py`'s (`|` -> `__`, `.jpg`, under
    `<store>/frames/`). Three resolution routes are tried in order and the failure names all of
    them, because a silently substituted frame would make every token count below meaningless.
    """
    tried: List[str] = []
    by_ref: Dict[str, Path] = {}
    if manifest is not None and manifest.exists():
        by_ref = _manifest_paths(manifest)
        tried.append("manifest %s (%d rows)" % (manifest, len(by_ref)))
    elif manifest is not None:
        tried.append("manifest %s (absent)" % manifest)
    log = store / "encode_log.jsonl"
    if not by_ref and log.exists():
        for ln in open(log):
            r = json.loads(ln)
            by_ref[str(r["frame_ref"])] = store / "frames" / str(r["file"])
        tried.append("encode_log %s (%d rows)" % (log, len(by_ref)))
    elif not by_ref:
        tried.append("encode_log %s (absent)" % log)

    stride = 2.0
    ts = [round(k * stride, 2) for k in range(int(t_ask / stride) + 1)]
    refs = ["%s|f%08.2f" % (session_id, t) for t in ts]
    if by_ref:
        have = [(r, by_ref[r]) for r in refs if r in by_ref and by_ref[r].exists()]
        route = "ref index"
    else:
        fdir = store / "frames"
        tried.append("name convention under %s" % fdir)
        have = []
        for r in refs:
            p = fdir / (r.replace("|", "__").replace("/", "_") + ".jpg")
            if p.exists():
                have.append((r, p))
        route = "name convention"
    if len(have) < n_frames:
        raise Stop("MISSING round-1 D2 frames for session %r: found %d of the %d needed.\n"
                   "  routes tried: %s\n"
                   "  this script does not synthesise frames outside --dry. Point --frames-dir "
                   "at the round-1 store (default %s) or --frame-manifest at the part-2 manifest "
                   "(default %s)." %
                   (session_id, len(have), n_frames, "; ".join(tried), D2_STORE,
                    COMBINED_MANIFEST))
    use = have[-int(n_frames):]
    return ([dict(frame_ref=r, path=p) for r, p in use],
            dict(route=route, routes_tried=tried, n_available=len(have), n_used=len(use),
                 first_ref=use[0][0], last_ref=use[-1][0],
                 bytes_total=sum(p.stat().st_size for _r, p in use)))


def dry_frames(session_id: str, n_frames: int, scratch: Path) -> Tuple[List[Dict[str, Any]],
                                                                      Dict[str, Any]]:
    """DRY ONLY. Writes `n_frames` copies of one minimal JPEG so the real body builder, the real
    uuid convention and the real wire form are all exercised with no round-1 data present."""
    d = scratch / "dry_frames"
    d.mkdir(parents=True, exist_ok=True)
    frames = []
    for k in range(int(n_frames)):
        ref = "%s|f%08.2f" % (session_id, 2.0 * k)
        p = d / (ref.replace("|", "__") + ".jpg")
        if not p.exists():
            p.write_bytes(_DRY_JPEG)
        frames.append(dict(frame_ref=ref, path=p))
    return frames, dict(route="DRY SYNTHETIC: %d copies of a %d-byte placeholder JPEG under %s; "
                              "NOT round-1 data and never sent to a real engine"
                              % (n_frames, len(_DRY_JPEG), d),
                        n_available=n_frames, n_used=n_frames,
                        bytes_total=len(_DRY_JPEG) * n_frames)


class History:
    """One device's copy of one session's history, and the three bodies it can send.

    Every arm of every measurement is a DISTINCT device_id, which under D84 gives it its own
    `cache_salt` and its own per-frame mm uuid, so two arms over the same JPEG files are
    cache-isolated by construction while carrying identical token counts. That is what makes the
    cold comparison arms in M1 and M3 fair rather than merely cold.
    """

    def __init__(self, tag: str, run_tag: str, session_id: str,
                 frames: Sequence[Dict[str, Any]], question: Dict[str, Any],
                 model: str, est_per_frame: int = D2_TOK_PER_IMG) -> None:
        self.tag = tag
        self.device_id = "c32b-%s" % tag
        self.run_tag = run_tag
        self.session_id = session_id
        self.frames = list(frames)
        self.question = question
        self.model = model
        self.salt = CK.cache_salt(run_tag, self.device_id)
        self.est_per_frame = int(est_per_frame)

    @property
    def est_tokens(self) -> int:
        return D2_HEADER_TOK + self.est_per_frame * len(self.frames)

    def _frames(self, upto: int, n_new: int) -> List[Dict[str, Any]]:
        """`upto` frames already uploaded (sent as uuid-only references, the committed StudyRH7
        wire form) plus the next `n_new` sent with bytes."""
        refs = [dict(frame_ref=f["frame_ref"], path=None) for f in self.frames[:upto]]
        new = [dict(f) for f in self.frames[upto:upto + n_new]]
        return refs + new

    def build_body(self, upto: int, n_new: int, *, salt: Optional[str] = None) -> Dict[str, Any]:
        """A prefill-only build piece: the committed build body (coordinator.py:752, header
        `D2 history`, max_tokens 1, kind piece/whole)."""
        fr = self._frames(upto, n_new)
        return _bb(kind="piece" if n_new < len(self.frames) else "whole",
                            device_id=self.device_id, session_id=self.session_id,
                            run_tag=self.run_tag, salt=salt or self.salt, header=HEADER_TEXT,
                            frames=fr, question=None, options=(), max_tokens=1,
                            model=self.model, stream=True,
                            est_tokens=D2_HEADER_TOK + self.est_per_frame * (upto + n_new),
                            retain=True)

    def probe_body(self, *, salt: Optional[str] = None) -> Dict[str, Any]:
        """The full-prefix, uuid-references-only, max_tokens 1 request StudyENG1c uses as its
        touch and residency probe. It uploads no bytes, so what it costs is KV, not pixels."""
        return _bb(kind="touch", device_id=self.device_id, session_id=self.session_id,
                            run_tag=self.run_tag, salt=salt or self.salt, header=HEADER_TEXT,
                            frames=self._frames(len(self.frames), 0), question=None, options=(),
                            max_tokens=1, model=self.model, stream=True,
                            est_tokens=self.est_tokens, retain=True)

    def question_body(self, *, refs_only: bool) -> Dict[str, Any]:
        """The committed StudyR1 recall body over this history (bodies.py kind='recall': StudyO's
        own question wrapper, StudyR1 cell K1's generation parameters)."""
        fr = (self._frames(len(self.frames), 0) if refs_only
              else self._frames(0, len(self.frames)))
        return _bb(kind="recall", device_id=self.device_id, session_id=self.session_id,
                            run_tag=self.run_tag, salt=self.salt, header=HEADER_TEXT, frames=fr,
                            question=self.question["question"],
                            options=self.question["options"],
                            max_tokens=B.RECALL_GEN["max_tokens"], model=self.model, stream=True,
                            est_tokens=self.est_tokens, retain=True)


# ---------------------------------------------------------------------------- filler traffic
_VOCAB = ("warehouse inventory pallet shelf aisle forklift carton label barcode operator "
          "corridor doorway camera timestamp sequence fragment residue cabinet drawer handle "
          "clipboard register manifest batch crate conveyor scanner bracket bolt washer").split()


class Filler:
    """Other traffic, used only to drive KV pressure.

    IT IS TEXT, AND THAT IS A DECLARED PROXY. What M2 and M3 need from "other traffic" is
    occupancy of the engine's KV pool and movement of its LRU frontier, which a text prompt
    produces exactly as an image prompt does: a block is a block. It is NOT a proxy for fleet
    traffic composition, and no number in this script is read as a fleet result. Text is chosen
    because it costs no vision encode, so the pressure is produced inside the break's budget.
    """

    def __init__(self, engine: Engine, run_tag: str, model: str, seed: int) -> None:
        self.e = engine
        self.run_tag = run_tag
        self.model = model
        self.rng = random.Random(seed)
        self.n = 0
        self.chars_per_token: Optional[float] = None
        self.tokens_sent = 0
        self.seconds = 0.0

    def _text(self, n_chars: int) -> str:
        words = [self.rng.choice(_VOCAB) for _ in range(max(int(n_chars / 7), 8))]
        return "f%d " % self.n + " ".join(words)

    def one(self, target_tokens: int, phase: str, role: str) -> Dict[str, Any]:
        # Until the engine has told us how many tokens a character of this text costs, assume the
        # DENSE end (2.5 chars per token) and keep the first request small. A filler that
        # overshoots --max-model-len is an HTTP 400 that would stop the whole confirmation, and
        # the first request is the cheapest possible place to learn the real rate.
        if self.chars_per_token is None:
            cpt, target_tokens = 2.5, min(int(target_tokens), 4_000)
        else:
            cpt = self.chars_per_token
            target_tokens = int(min(target_tokens, (MAX_MODEL_LEN - 2_048) * 0.9))
        n_chars = int(max(target_tokens, 64) * cpt)
        self.n += 1
        dev = "c32b-fill%04d" % self.n
        body = _bb(kind="whole", device_id=dev, session_id=None, run_tag=self.run_tag,
                            salt=CK.cache_salt(self.run_tag, dev), header=self._text(n_chars),
                            frames=(), question=None, options=(), max_tokens=1,
                            model=self.model, stream=True, est_tokens=target_tokens, retain=True)
        t0 = time.time()
        row = self.e.send(body, role=role, phase=phase,
                          cache=dict(prefix_caching="ON", condition="COLD",
                                     cached_before="nothing: a fresh device salt and text never "
                                                   "sent before",
                                     repeat_servable_from_cache=True,
                                     note="filler; occupancy only, not a measurement"),
                          extra=dict(target_tokens=int(target_tokens), chars=len(body["messages"]
                                                                                [0]["content"][0]
                                                                                ["text"])))
        self.seconds += time.time() - t0
        pt = row["prompt_tokens"]
        if pt:
            self.tokens_sent += int(pt)
            self.chars_per_token = row["chars"] / float(pt)
        return row

    def drive(self, target_tokens: int, phase: str, role: str = "filler",
              per_request: int = 24_000, budget: Optional[Budget] = None) -> Dict[str, Any]:
        """Issue fresh traffic until `target_tokens` prompt tokens have been charged."""
        per_request = int(min(per_request, MAX_MODEL_LEN - 1_024))
        done, n0, t0 = 0, self.n, time.time()
        rows = []
        while done < target_tokens:
            if budget is not None and budget.left < 20.0:
                break
            want = int(min(per_request, max(target_tokens - done, 256)))
            r = self.one(want, phase, role)
            rows.append(r)
            done += int(r["prompt_tokens"] or r["target_tokens"])
        el = time.time() - t0
        return dict(target_tokens=int(target_tokens), tokens_charged=int(done),
                    n_requests=self.n - n0, seconds=round(el, 3),
                    tokens_per_s=(round(done / el, 1) if el > 0 else None),
                    prompt_tokens_known=all(r["prompt_tokens"] is not None for r in rows))


# ---------------------------------------------------------------------------- preflight
def preflight(e: Engine, args: argparse.Namespace, run_tag: str) -> Dict[str, Any]:
    """Server identity, the residency channels, and a prefix-cache POSITIVE CONTROL.

    The control is the thing that makes every later cached-token number readable: a same-salt
    repeat MUST report reuse and a fresh-salt repeat MUST NOT. If the first fails, prefix caching
    is off or `cached_tokens` is not reported, and all three measurements are NOT ESTABLISHED
    rather than silently zero. CLAUDE.md consistency check 7: an impossible success and an
    impossible failure are equally diagnostic, so both directions are asserted.
    """
    out: Dict[str, Any] = dict(base_url=e.base_url, served_model=e.served_model)
    try:
        models = e.models()
        ids = [m.get("id") for m in models.get("data", [])]
        out["model_ids"] = ids
        out["served_model_present"] = e.served_model in ids
        if not out["served_model_present"]:
            raise Stop("the server at %s serves %r, not %r. Point --base-url at the round-1 32B "
                       "server (port 8031, --served-model-name 32BI) or pass --served-model."
                       % (e.base_url, ids, e.served_model))
    except Stop:
        raise
    except Exception as ex:                                              # noqa: BLE001
        raise Stop("cannot reach %s/v1/models: %r. The server must already be running; this "
                   "script starts nothing." % (e.base_url, ex))

    try:
        raw = e.get("/metrics")
        e.metrics_available = True
        m = _flatten_metrics(raw)
    except Exception as ex:                                              # noqa: BLE001
        m = {}
        out["metrics_error"] = repr(ex)
    out["metrics_keys"] = sorted(m)
    out["residency_channels"] = dict(
        prompt_tokens_by_source=all(k in m for k in (SRC_LOCAL, SRC_EXTERNAL, SRC_COMPUTE)),
        external_prefix_cache=(EXT_HITS in m),
        gpu_cache_usage=any("gpu_cache_usage" in k or "kv_cache_usage" in k for k in m))
    out["metrics_at_start"] = {k: m[k] for k in sorted(m)
                               if "prompt_tokens_by_source" in k or "prefix_cache" in k
                               or "cache_usage" in k}
    out["host_residency_channel_available"] = bool(
        out["residency_channels"]["prompt_tokens_by_source"]
        or out["residency_channels"]["external_prefix_cache"])

    # the positive control: ~600 tokens of text, three sends
    dev, dev_b = "c32b-ctl", "c32b-ctl-fresh"
    salt_a, salt_b = CK.cache_salt(run_tag, dev), CK.cache_salt(run_tag, dev_b)
    text = "control " + " ".join(_VOCAB * 24)

    def ctl(salt: str, role: str, cache: Dict[str, Any]) -> Dict[str, Any]:
        body = _bb(kind="whole", device_id=(dev if salt == salt_a else dev_b),
                   session_id=None, run_tag=run_tag,
                            salt=salt, header=text, frames=(), question=None, options=(),
                            max_tokens=1, model=e.served_model, stream=True, est_tokens=600,
                            retain=True)
        return e.send(body, role=role, phase="preflight", cache=cache, with_metrics=True)

    first = ctl(salt_a, "control_first_send",
                dict(prefix_caching="ON", condition="COLD",
                     cached_before="nothing: this salt and this text are new to the engine",
                     repeat_servable_from_cache=True))
    repeat = ctl(salt_a, "control_same_salt_repeat",
                 dict(prefix_caching="ON", condition="WARM",
                      cached_before="the identical body, sent immediately before under the same "
                                    "salt",
                      repeat_servable_from_cache=True))
    fresh = ctl(salt_b, "control_fresh_salt_repeat",
                dict(prefix_caching="ON", condition="COLD",
                     cached_before="the same TEXT under a different cache_salt, which D84 makes a "
                                   "different prefix chain",
                     repeat_servable_from_cache=True))
    out["positive_control"] = dict(
        first_cached_tokens=first["cached_tokens"], repeat_cached_tokens=repeat["cached_tokens"],
        fresh_salt_cached_tokens=fresh["cached_tokens"],
        prompt_tokens=repeat["prompt_tokens"],
        raw_usage_block_of_repeat=repeat["usage_keys"],
        external_hit_keys_probed=list(EA.EXTERNAL_HIT_KEYS),
        external_cached_tokens_of_repeat=repeat["external_cached_tokens"])
    ct_rep, ct_fresh = repeat["cached_tokens"], fresh["cached_tokens"]
    if ct_rep is None:
        out["positive_control"]["verdict"] = "NO EVIDENCE: the server reported no " \
            "prompt_tokens_details.cached_tokens, so no cached-token measurement is possible"
    elif ct_rep <= COLD_OK_CACHED_MAX:
        out["positive_control"]["verdict"] = "FAIL: a same-salt repeat reused %s tokens of %s. " \
            "Prefix caching is not serving repeats on this server." % (ct_rep,
                                                                       repeat["prompt_tokens"])
    elif ct_fresh is not None and ct_fresh > COLD_OK_CACHED_MAX:
        out["positive_control"]["verdict"] = "FAIL: a FRESH-SALT repeat reused %s tokens, so the " \
            "salt is not isolating prefixes and no 'cold' arm in this script is cold." % ct_fresh
    else:
        out["positive_control"]["verdict"] = "PASS"
    out["ok"] = out["positive_control"]["verdict"] == "PASS"
    return out


# ---------------------------------------------------------------------------- M1
def measure_m1(e: Engine, args: argparse.Namespace, run_tag: str, frames, question,
               budget: Budget) -> Dict[str, Any]:
    """Warm-ahead raises cached tokens at question time."""
    slice_frames = max(int(args.slice_frames), 1)
    reps: List[Dict[str, Any]] = []
    per_rep_s = 14.0
    for i in range(int(args.m1_reps)):
        if not budget.have(per_rep_s, "M1 rep %d" % i):
            break
        warm = History("m1w%d" % i, run_tag, question["session_id"], frames, question,
                       e.served_model)
        cold = History("m1c%d" % i, run_tag, question["session_id"], frames, question,
                       e.served_model)
        # --- the warm-ahead arm: prefill-only pieces, ahead of any question
        pieces = []
        upto = 0
        t0 = time.time()
        while upto < len(frames):
            n_new = min(slice_frames, len(frames) - upto)
            r = e.send(warm.build_body(upto, n_new), role="warm_ahead_piece", phase="M1",
                       cache=dict(prefix_caching="ON",
                                  condition=("COLD" if upto == 0 else "WARM"),
                                  cached_before=("nothing: first piece on a fresh device salt"
                                                 if upto == 0 else
                                                 "this device's own %d-frame prefix, prefilled by "
                                                 "the previous piece" % upto),
                                  repeat_servable_from_cache=True),
                       extra=dict(rep=i, piece=len(pieces), frames_before=upto, n_new=n_new))
            pieces.append(r)
            upto += n_new
        warm_build_s = time.time() - t0
        q_warm = e.send(warm.question_body(refs_only=True), role="question_after_warm_ahead",
                        phase="M1", with_metrics=True,
                        cache=dict(prefix_caching="ON", condition="WARM",
                                   cached_before="this device's whole %d-frame history, prefilled "
                                                 "ahead of the question by %d prefill-only pieces"
                                                 % (len(frames), len(pieces)),
                                   repeat_servable_from_cache=True),
                        extra=dict(rep=i))
        # --- the comparison arm: same question, same frames, no warm-ahead
        q_cold = e.send(cold.question_body(refs_only=False), role="question_without_warm_ahead",
                        phase="M1", with_metrics=True,
                        cache=dict(prefix_caching="ON", condition="COLD",
                                   cached_before="nothing of this device's: its cache_salt and "
                                                 "every one of its mm uuids are new to the engine "
                                                 "(D84). The JPEG bytes are the same files the "
                                                 "warm arm used.",
                                   repeat_servable_from_cache=True),
                        extra=dict(rep=i))
        reps.append(dict(
            rep=i, n_pieces=len(pieces), warm_build_s=round(warm_build_s, 3),
            warm_cached_tokens=q_warm["cached_tokens"], warm_prompt_tokens=q_warm["prompt_tokens"],
            warm_ttft_s=q_warm["ttft_s"], warm_total_s=q_warm["total_s"],
            warm_residency=q_warm["residency_class"],
            cold_cached_tokens=q_cold["cached_tokens"], cold_prompt_tokens=q_cold["prompt_tokens"],
            cold_ttft_s=q_cold["ttft_s"], cold_total_s=q_cold["total_s"],
            cold_residency=q_cold["residency_class"]))

    res: Dict[str, Any] = dict(
        claim="a warm-ahead prefill of a session's uploaded frames raises the engine's reported "
              "cached_tokens for the question that follows",
        design=dict(
            warm_arm="one device, %d frames prefilled ahead of the question as %s-frame "
                     "prefill-only pieces (engine_actions.WARM_AHEAD_SLICE_TOKENS discipline), "
                     "then the committed StudyR1 recall body with every frame as a uuid-only "
                     "reference" % (len(frames), slice_frames),
            cold_arm="a different device, the same JPEG files, the same committed recall body, no "
                     "warm-ahead; D84 gives it its own cache_salt and its own mm uuids so its "
                     "prefix chain is new to the engine",
            declared_asymmetry="the warm arm's question uploads no image bytes (uuid-only "
                               "references, the committed StudyRH7 wire form) and the cold arm's "
                               "uploads all of them, because a uuid the engine has never seen "
                               "cannot be resolved. Request bytes are recorded per row. The TTFT "
                               "gap therefore contains avoided upload and vision encode as well "
                               "as avoided prefill, and must not be read as prefill alone.",
            pass_rule="cached_tokens on the warm arm >= %.2f * its prompt_tokens (StudyENG1c's "
                      "own 'gpu' threshold) AND cached_tokens on the cold arm <= %d (one vLLM "
                      "block, StudyENG1c's cold gate) AND warm > cold in every rep"
                      % (GPU_CLASSIFY_FRAC, COLD_OK_CACHED_MAX)),
        reps=reps)
    ok_reps = [r for r in reps if r["warm_cached_tokens"] is not None
               and r["warm_prompt_tokens"]]
    if not reps:
        res.update(verdict="NOT ATTEMPTED (budget)", established=False)
    elif not ok_reps:
        res.update(verdict="NOT ESTABLISHED", established=False,
                   reason="the server reported no prompt_tokens_details.cached_tokens, so the "
                          "quantity the claim is about was never observed")
    else:
        warm_frac = [r["warm_cached_tokens"] / float(r["warm_prompt_tokens"]) for r in ok_reps]
        cold = [r["cold_cached_tokens"] for r in ok_reps if r["cold_cached_tokens"] is not None]
        strict = all(r["cold_cached_tokens"] is not None
                     and r["warm_cached_tokens"] > r["cold_cached_tokens"] for r in ok_reps)
        passed = (min(warm_frac) >= GPU_CLASSIFY_FRAC and bool(cold)
                  and max(cold) <= COLD_OK_CACHED_MAX and strict)
        res.update(
            n_reps=len(ok_reps),
            warm_cached_fraction=dict(min=round(min(warm_frac), 4), median=round(
                statistics.median(warm_frac), 4), max=round(max(warm_frac), 4)),
            warm_cached_tokens=[r["warm_cached_tokens"] for r in ok_reps],
            cold_cached_tokens=[r["cold_cached_tokens"] for r in ok_reps],
            warm_ttft_s=[r["warm_ttft_s"] for r in ok_reps],
            cold_ttft_s=[r["cold_ttft_s"] for r in ok_reps],
            prompt_tokens=[r["warm_prompt_tokens"] for r in ok_reps],
            established=bool(passed),
            verdict=("PASS" if passed else "FAIL"))
    return res


# ---------------------------------------------------------------------------- frontier
def calibrate_frontier(e: Engine, args: argparse.Namespace, run_tag: str, unit_tokens: int,
                       budget: Budget) -> Dict[str, Any]:
    """MEASURE the engine's eviction frontier, in units of one history, on the live server.

    Why this is measured and not computed. The committed pool sizes are GPU 62,944 tokens and a
    27 GiB host tier = 110,592 tokens (ENG1c: a C GiB cap holds C * 4096 tokens). Whether the
    observable reuse window is their SUM (store-on-eviction: a hit may be served from either
    tier) or just the HOST window (write-through: the host holds a superset of the GPU) is a
    1.57x difference, and M2 needs the frontier to one history's accuracy. So a ladder of
    `--ladder-units` text sentinels of one history's size each is built oldest to newest and then
    probed YOUNGEST FIRST, stopping at the first miss: probing the youngest costs nothing but a
    cache hit, so the ladder is not disturbed while it is being read, and the walk stops before
    the first miss would rebuild anything.
    """
    units = int(args.ladder_units)
    sents: List[Tuple[str, Dict[str, Any]]] = []
    t0 = time.time()
    for k in range(units):
        if not budget.have(6.0, "frontier ladder rung %d" % k):
            break
        dev = "c32b-lad%03d" % k
        salt = CK.cache_salt(run_tag, dev)
        text = "ladder %d " % k + " ".join(
            random.Random(9000 + k).choice(_VOCAB)
            for _ in range(max(int(unit_tokens * 4.0 / 7), 16)))
        body = _bb(kind="whole", device_id=dev, session_id=None, run_tag=run_tag,
                            salt=salt, header=text, frames=(), question=None, options=(),
                            max_tokens=1, model=e.served_model, stream=True,
                            est_tokens=unit_tokens, retain=True)
        r = e.send(body, role="ladder_build", phase="frontier",
                   cache=dict(prefix_caching="ON", condition="COLD",
                              cached_before="nothing: a fresh salt and fresh text",
                              repeat_servable_from_cache=True),
                   extra=dict(rung=k))
        sents.append((dev, body))
    build_s = time.time() - t0
    hits, probes = 0, []
    for k in range(len(sents) - 1, -1, -1):
        if not budget.have(4.0, "frontier probe rung %d" % k):
            break
        dev, body = sents[k]
        r = e.send(dict(body), role="ladder_probe", phase="frontier", with_metrics=True,
                   cache=dict(prefix_caching="ON", condition="UNKNOWN BY DESIGN",
                              cached_before="this rung was built %d rungs ago; whether it is "
                                            "still resident is what is being measured"
                                            % (len(sents) - 1 - k),
                              repeat_servable_from_cache=True),
                   extra=dict(rung=k, depth=len(sents) - 1 - k))
        ct = r["cached_tokens"]
        probes.append(dict(rung=k, depth=len(sents) - 1 - k, cached_tokens=ct,
                           prompt_tokens=r["prompt_tokens"], residency=r["residency_class"]))
        if ct is None or ct <= COLD_OK_CACHED_MAX:
            break
        hits += 1
    out = dict(
        unit_tokens=int(unit_tokens), ladder_units=len(sents), build_seconds=round(build_s, 3),
        probes=probes, frontier_units=hits, frontier_tokens=hits * int(unit_tokens),
        committed_gpu_pool_tokens=GPU_POOL_TOKENS,
        committed_host_tier_tokens=HOST_CAP_TOKENS,
        hypothesis_sum_tokens=GPU_POOL_TOKENS + HOST_CAP_TOKENS,
        hypothesis_host_only_tokens=HOST_CAP_TOKENS,
        note="frontier_units is the number of one-history units at the YOUNG end of the ladder "
             "that still reported reuse. It is measured on this server at this moment and is the "
             "only capacity figure M2 relies on.")
    if hits == 0:
        out["verdict"] = ("NOT ESTABLISHED: even the youngest rung reported no reuse, so either "
                          "cached_tokens is unavailable or the ladder rung does not fit; M2 "
                          "cannot size its traffic")
    elif hits >= len(sents):
        out["verdict"] = ("NOT ESTABLISHED: every rung still reported reuse, so the ladder "
                          "(%d units, %d tokens) never reached the frontier; raise "
                          "--ladder-units" % (len(sents), len(sents) * unit_tokens))
    else:
        out["verdict"] = "MEASURED"
        s, h = out["hypothesis_sum_tokens"], out["hypothesis_host_only_tokens"]
        out["closer_to"] = ("GPU+host sum" if abs(out["frontier_tokens"] - s)
                            <= abs(out["frontier_tokens"] - h) else "host window only")
    return out


# ---------------------------------------------------------------------------- M2
def measure_m2(e: Engine, args: argparse.Namespace, run_tag: str, frames, question,
               frontier: Dict[str, Any], filler: Filler, budget: Budget) -> Dict[str, Any]:
    """A touched history survives where an untouched one is evicted."""
    res: Dict[str, Any] = dict(
        claim="a history whose prefix has been re-read moves DOWN the engine's eviction order, so "
              "under pressure that evicts exactly one of two histories it is the untouched one "
              "that goes",
        design=dict(
            engine_level_touch="a full-prefix, uuid-references-only, max_tokens 1 request, which "
                               "is StudyENG1c's own touch probe. It uploads no bytes and emits no "
                               "answer; all it does is read the prefix, which is the only way a "
                               "client can move vLLM's LRU.",
            conditions="TOUCH builds T then U then touches T, so the recency order youngest-first "
                       "is (T, U). NOTOUCH builds T then U and touches nothing, so it is (U, T). "
                       "Both conditions then take the SAME amount of filler traffic and the same "
                       "probes, so the two predict OPPOSITE winners and a flood that is mis-sized "
                       "cannot manufacture the asymmetry.",
            flood_rule="(frontier_units - 1) histories' worth of fresh traffic, from the MEASURED "
                       "frontier, so that exactly one of the two histories falls past it",
            honesty="vLLM cannot pin KV (D150), so this is a probability and not a promise. The "
                    "result is COUNTS over repetitions. A repetition in which both histories hit "
                    "or both miss is INDETERMINATE: the pressure missed the one-history window, "
                    "which is evidence about the sizing and not about the touch.",
            pass_rule="in TOUCH, T hits and U misses in strictly more repetitions than the "
                      "reverse; AND the NOTOUCH control shows the reverse asymmetry or no "
                      "asymmetry. If NOTOUCH shows the SAME winner as TOUCH, the touch is not "
                      "what moved it."))
    if frontier.get("verdict") != "MEASURED":
        res.update(verdict="NOT ESTABLISHED", established=False,
                   reason="the eviction frontier was not measured (%s), so the pressure cannot be "
                          "sized to evict exactly one of two histories"
                          % frontier.get("verdict"))
        return res
    unit = int(frontier["unit_tokens"])
    flood_units = max(int(frontier["frontier_units"]) - 1, 1)
    reps: List[Dict[str, Any]] = []
    per_rep_s = 14.0 + unit * flood_units / 6_000.0
    for i in range(int(args.m2_reps)):
        for cond in ("TOUCH", "NOTOUCH"):
            if not budget.have(per_rep_s, "M2 %s rep %d" % (cond, i)):
                break
            T = History("m2t%s%d" % (cond[0].lower(), i), run_tag, question["session_id"],
                        frames, question, e.served_model)
            U = History("m2u%s%d" % (cond[0].lower(), i), run_tag, question["session_id"],
                        frames, question, e.served_model)
            bT = e.send(T.build_body(0, len(frames)), role="build_T", phase="M2",
                        cache=dict(prefix_caching="ON", condition="COLD",
                                   cached_before="nothing: fresh device salt and fresh mm uuids",
                                   repeat_servable_from_cache=True),
                        extra=dict(rep=i, condition=cond))
            bU = e.send(U.build_body(0, len(frames)), role="build_U", phase="M2",
                        cache=dict(prefix_caching="ON", condition="COLD",
                                   cached_before="nothing: fresh device salt and fresh mm uuids",
                                   repeat_servable_from_cache=True),
                        extra=dict(rep=i, condition=cond))
            touched = None
            if cond == "TOUCH":
                touched = e.send(T.probe_body(), role="touch_T", phase="M2", with_metrics=True,
                                 cache=dict(prefix_caching="ON", condition="WARM",
                                            cached_before="T's own history, built moments ago",
                                            repeat_servable_from_cache=True),
                                 extra=dict(rep=i, condition=cond))
            flood = filler.drive(flood_units * unit, "M2", role="pressure", budget=budget)
            pT = e.send(T.probe_body(), role="probe_T", phase="M2", with_metrics=True,
                        cache=dict(prefix_caching="ON", condition="UNKNOWN BY DESIGN",
                                   cached_before="T's history was built, %s, and then %d tokens "
                                                 "of other traffic were driven through the engine; "
                                                 "whether it survived is the measurement"
                                                 % ("touched" if cond == "TOUCH" else "not touched",
                                                    flood["tokens_charged"]),
                                   repeat_servable_from_cache=True),
                        extra=dict(rep=i, condition=cond))
            pU = e.send(U.probe_body(), role="probe_U", phase="M2", with_metrics=True,
                        cache=dict(prefix_caching="ON", condition="UNKNOWN BY DESIGN",
                                   cached_before="U's history was built and never touched, then "
                                                 "%d tokens of other traffic were driven through "
                                                 "the engine" % flood["tokens_charged"],
                                   repeat_servable_from_cache=True),
                        extra=dict(rep=i, condition=cond))

            def hit(r: Dict[str, Any]) -> Optional[bool]:
                ct = r["cached_tokens"]
                return None if ct is None else bool(ct > COLD_OK_CACHED_MAX)
            hT, hU = hit(pT), hit(pU)
            if hT is None or hU is None:
                outcome = "NO EVIDENCE"
            elif hT and not hU:
                outcome = "T_SURVIVED"
            elif hU and not hT:
                outcome = "U_SURVIVED"
            else:
                outcome = "INDETERMINATE"
            reps.append(dict(rep=i, condition=cond, outcome=outcome,
                             touched=("T" if cond == "TOUCH" else None),
                             flood=flood, flood_units=flood_units,
                             build_T_cached=bT["cached_tokens"], build_U_cached=bU["cached_tokens"],
                             touch_cached=(touched or {}).get("cached_tokens"),
                             T_cached_tokens=pT["cached_tokens"], U_cached_tokens=pU["cached_tokens"],
                             T_prompt_tokens=pT["prompt_tokens"], U_prompt_tokens=pU["prompt_tokens"],
                             T_residency=pT["residency_class"], U_residency=pU["residency_class"],
                             T_ttft_s=pT["ttft_s"], U_ttft_s=pU["ttft_s"]))
    res["reps"] = reps

    def tally(cond: str) -> Dict[str, int]:
        rr = [r for r in reps if r["condition"] == cond]
        return dict(n=len(rr), T_survived=sum(1 for r in rr if r["outcome"] == "T_SURVIVED"),
                    U_survived=sum(1 for r in rr if r["outcome"] == "U_SURVIVED"),
                    indeterminate=sum(1 for r in rr if r["outcome"] == "INDETERMINATE"),
                    no_evidence=sum(1 for r in rr if r["outcome"] == "NO EVIDENCE"))
    t, n = tally("TOUCH"), tally("NOTOUCH")
    res["counts"] = dict(TOUCH=t, NOTOUCH=n)
    if not reps:
        res.update(verdict="NOT ATTEMPTED (budget)", established=False)
    elif t["n"] == 0 or t["T_survived"] + t["U_survived"] == 0:
        res.update(verdict="NOT ESTABLISHED", established=False,
                   reason="no TOUCH repetition produced a decided outcome (%s); the pressure did "
                          "not land inside the one-history window, or the engine reported no "
                          "cached_tokens. CLAUDE.md Rule 2: this is INCONCLUSIVE, unexercised, "
                          "not a negative." % t)
    else:
        treatment = t["T_survived"] > t["U_survived"]
        control_same = n["T_survived"] > n["U_survived"]
        passed = bool(treatment and not control_same)
        res.update(established=passed, verdict=("PASS" if passed else "FAIL"),
                   decided_touch=t["T_survived"] + t["U_survived"],
                   exact_binomial_p_touch=_binom_p(t["T_survived"],
                                                   t["T_survived"] + t["U_survived"]),
                   statistical_note="with %d decided TOUCH repetitions the strongest available "
                                    "statement is a count; the exact one-sided binomial p against "
                                    "a fair coin is reported beside it and nothing stronger is "
                                    "claimed." % (t["T_survived"] + t["U_survived"]))
        if control_same:
            res["reason"] = ("the NOTOUCH control shows the SAME winner as TOUCH, so something "
                             "other than the touch is deciding which history survives")
    return res


def _binom_p(k: int, n: int) -> Optional[float]:
    """Exact one-sided binomial tail P(X >= k) at p = 0.5, computed with integers."""
    if n <= 0:
        return None
    from math import comb
    return round(sum(comb(n, j) for j in range(k, n + 1)) / float(2 ** n), 6)


# ---------------------------------------------------------------------------- M3
def measure_m3(e: Engine, args: argparse.Namespace, run_tag: str, frames, question,
               frontier: Dict[str, Any], filler: Filler, preflight_res: Dict[str, Any],
               budget: Budget, dry: bool = False) -> Dict[str, Any]:
    """Reload-from-host against a cold rebuild, with host residency verified first."""
    res: Dict[str, Any] = dict(
        claim="making a history resident again from the HOST tier is faster than rebuilding it "
              "from scratch",
        trigger_state_note="across 56 committed 16-device cells the coordinator's believed_tier is "
                           "NEVER host (reports/study_engine_actions.md section 2), so this "
                           "action's trigger state has never been observed in our harness. This "
                           "measurement CREATES the host-resident condition on the engine and "
                           "verifies it; it does not observe the harness reaching it, and must "
                           "never be cited as if it did.",
        design=dict(
            how_host_residency_is_created="build the history, then drive enough other traffic to "
                                          "push it out of the %d-token GPU pool while staying "
                                          "inside the measured reuse frontier, so the native "
                                          "offload tier (27 GiB = %d tokens) still holds it"
                                          % (GPU_POOL_TOKENS, HOST_CAP_TOKENS),
            how_it_is_verified="a TWIN history built and pressured identically is probed first, "
                               "and its residency is classified by StudyENG1c's committed rule "
                               "over the server's prompt_tokens_by_source / "
                               "external_prefix_cache counters. The timed reload's OWN counter "
                               "delta is then classified too, and both must say host or "
                               "partial_host for the repetition to count.",
            why_a_twin="probing a history reloads it, so the condition cannot be verified on the "
                       "same object that is then timed. The twin is built immediately after it, "
                       "from the same frames on its own device salt, and takes the same pressure.",
            comparators=dict(
                RELOAD="the host-resident history, full prefix as uuid references, max_tokens 1",
                COLD_KV="the SAME uuids under a DIFFERENT cache_salt, so the mm processor cache "
                        "still holds the frames but the whole KV prefix chain is a new key (D84). "
                        "This isolates KV reconstruction with no byte upload and no vision "
                        "re-encode.",
                COLD_FULL="a fresh device: new salt, new uuids, every frame's bytes on the wire. "
                          "This is what the fleet actually pays for a cold rebuild and it is the "
                          "headline comparator."),
            pass_rule="at least one repetition verified host-resident on BOTH channels, and the "
                      "median RELOAD time below the median COLD_FULL time. Repetitions that fail "
                      "verification are DISCARDED and counted, never timed as reloads."))
    if not preflight_res.get("host_residency_channel_available") and not dry:
        res.update(verdict="NOT ESTABLISHED", established=False,
                   reason="this server exposes neither prompt_tokens_by_source nor "
                          "external_prefix_cache_* in /metrics, so host residency cannot be "
                          "verified. Per the brief, nothing is timed and called a reload.")
        return res
    if frontier.get("verdict") != "MEASURED":
        res.update(verdict="NOT ESTABLISHED", established=False,
                   reason="the reuse frontier was not measured (%s), so the pressure that must "
                          "evict from GPU without evicting from host cannot be sized"
                          % frontier.get("verdict"))
        return res
    unit = int(frontier["unit_tokens"])
    flood_tokens = int(args.m3_flood_tokens
                       or (3 * unit if dry else int(GPU_POOL_TOKENS * 1.2)))
    room = int(frontier["frontier_tokens"]) - (flood_tokens + 2 * unit)
    reps: List[Dict[str, Any]] = []
    per_rep_s = 18.0 + flood_tokens / 6_000.0
    for i in range(int(args.m3_reps)):
        if not budget.have(per_rep_s, "M3 rep %d" % i):
            break
        twin = History("m3v%d" % i, run_tag, question["session_id"], frames, question,
                       e.served_model)
        subj = History("m3s%d" % i, run_tag, question["session_id"], frames, question,
                       e.served_model)
        cold_dev = History("m3c%d" % i, run_tag, question["session_id"], frames, question,
                           e.served_model)
        build_cache = dict(prefix_caching="ON", condition="COLD",
                           cached_before="nothing: fresh device salt, fresh mm uuids",
                           repeat_servable_from_cache=True)
        bv = e.send(twin.build_body(0, len(frames)), role="build_twin", phase="M3",
                    cache=build_cache, extra=dict(rep=i))
        bs = e.send(subj.build_body(0, len(frames)), role="build_subject", phase="M3",
                    cache=build_cache, extra=dict(rep=i))
        flood = filler.drive(flood_tokens, "M3", role="gpu_pressure", budget=budget)
        verify = e.send(twin.probe_body(), role="verify_twin_residency", phase="M3",
                        with_metrics=True,
                        cache=dict(prefix_caching="ON", condition="UNKNOWN BY DESIGN",
                                   cached_before="the twin's history was built, then %d tokens of "
                                                 "other traffic pushed it out of the GPU pool; "
                                                 "where it is now is the measurement"
                                                 % flood["tokens_charged"],
                                   repeat_servable_from_cache=True),
                        extra=dict(rep=i))
        reload_row = e.send(subj.probe_body(), role="timed_reload", phase="M3", with_metrics=True,
                            cache=dict(prefix_caching="ON", condition="WARM (HOST TIER)",
                                       cached_before="the subject's own history, offloaded to the "
                                                     "host tier by the same pressure; this request "
                                                     "uploads no bytes",
                                       repeat_servable_from_cache=True),
                            extra=dict(rep=i))
        cold_kv = e.send(subj.probe_body(salt=CK.cache_salt(run_tag, subj.device_id + "-coldkv")),
                         role="timed_cold_kv", phase="M3", with_metrics=True,
                         cache=dict(prefix_caching="ON", condition="COLD (KV ONLY)",
                                    cached_before="the frames themselves, in the mm processor "
                                                  "cache, because the mm uuids are unchanged. The "
                                                  "KV prefix chain is a new key because the "
                                                  "cache_salt differs (D84), so no KV is reused.",
                                    repeat_servable_from_cache=True),
                         extra=dict(rep=i))
        cold_full = e.send(cold_dev.build_body(0, len(frames)), role="timed_cold_full", phase="M3",
                           with_metrics=True,
                           cache=dict(prefix_caching="ON", condition="COLD (FULL)",
                                      cached_before="nothing of this device's: new salt, new mm "
                                                    "uuids, every frame's bytes on the wire",
                                      repeat_servable_from_cache=True),
                           extra=dict(rep=i))
        vcls, rcls = verify["residency_class"], reload_row["residency_class"]
        verified = (vcls in ("host", "partial_host")) and (rcls in ("host", "partial_host"))
        reps.append(dict(
            rep=i, flood=flood, verified_host_resident=bool(verified),
            twin_residency=vcls, reload_residency=rcls,
            twin_cached_tokens=verify["cached_tokens"], twin_external=verify["m_external"],
            twin_local=verify["m_local"],
            reload_cached_tokens=reload_row["cached_tokens"],
            reload_external=reload_row["m_external"], reload_local=reload_row["m_local"],
            reload_ttft_s=reload_row["ttft_s"], reload_total_s=reload_row["total_s"],
            cold_kv_ttft_s=cold_kv["ttft_s"], cold_kv_total_s=cold_kv["total_s"],
            cold_kv_cached_tokens=cold_kv["cached_tokens"],
            cold_full_ttft_s=cold_full["ttft_s"], cold_full_total_s=cold_full["total_s"],
            cold_full_cached_tokens=cold_full["cached_tokens"],
            prompt_tokens=reload_row["prompt_tokens"],
            build_twin_cached=bv["cached_tokens"], build_subject_cached=bs["cached_tokens"]))
    res["reps"] = reps
    res["flood_tokens_per_rep"] = flood_tokens
    res["frontier_headroom_tokens"] = room
    if room <= 0:
        res["sizing_warning"] = (
            "the GPU pressure (%d tokens) plus the two histories (%d) is not comfortably inside "
            "the measured reuse frontier (%d tokens), so a repetition may read COLD because the "
            "history left the host tier too. Repetitions are verified individually, so this "
            "shows up as discarded repetitions rather than as a wrong number."
            % (flood_tokens, 2 * unit, frontier["frontier_tokens"]))
    good = [r for r in reps if r["verified_host_resident"]]
    res["n_reps"] = len(reps)
    res["n_verified"] = len(good)
    res["n_discarded_unverified"] = len(reps) - len(good)
    if not reps:
        res.update(verdict="NOT ATTEMPTED (budget)", established=False)
    elif not good:
        res.update(verdict="NOT ESTABLISHED", established=False,
                   reason="host residency was never verified: the twin probe classified as %s and "
                          "the timed request as %s across %d repetitions. Nothing here is a "
                          "reload timing. CLAUDE.md Rule 2: INCONCLUSIVE, unexercised."
                          % ([r["twin_residency"] for r in reps],
                             [r["reload_residency"] for r in reps], len(reps)))
    else:
        def med(key: str) -> Optional[float]:
            v = [r[key] for r in good if r[key] is not None]
            return round(statistics.median(v), 4) if v else None
        rl_t, ck_t, cf_t = med("reload_total_s"), med("cold_kv_total_s"), med("cold_full_total_s")
        rl_f, cf_f = med("reload_ttft_s"), med("cold_full_ttft_s")
        passed = bool(rl_t is not None and cf_t is not None and rl_t < cf_t)
        res.update(
            established=passed, verdict=("PASS" if passed else "FAIL"),
            median_reload_total_s=rl_t, median_cold_kv_total_s=ck_t,
            median_cold_full_total_s=cf_t,
            median_reload_ttft_s=rl_f, median_cold_full_ttft_s=cf_f,
            speedup_total_vs_cold_full=(round(cf_t / rl_t, 3) if rl_t and cf_t else None),
            speedup_total_vs_cold_kv=(round(ck_t / rl_t, 3) if rl_t and ck_t else None),
            speedup_ttft_vs_cold_full=(round(cf_f / rl_f, 3) if rl_f and cf_f else None),
            per_rep=[{k: r[k] for k in ("rep", "reload_total_s", "cold_kv_total_s",
                                        "cold_full_total_s", "reload_residency")} for r in good])
    return res


# ---------------------------------------------------------------------------- logic self-test
def selftest() -> Dict[str, Any]:
    """Exercise the DECISION rules on fixtures, so the --dry run proves more than plumbing.

    The CPU stub reports no cached tokens and no offload counters, so a dry run can only show
    that the script reaches each phase and refuses to conclude. These fixtures show that the rules
    it would apply to a real usage block are the rules this report claims, including that each one
    collapses the right way when the mechanism is removed.
    """
    cases: List[Dict[str, Any]] = []

    def case(name: str, got: Any, want: Any) -> None:
        cases.append(dict(case=name, got=got, want=want, ok=(got == want)))

    case("classify: full local reuse is gpu", classify_residency(11000, 0, 11191), "gpu")
    case("classify: reuse all from the connector is host",
         classify_residency(0, 11180, 11191), "host")
    case("classify: a trickle of external is partial_host",
         classify_residency(0, 200, 11191), "partial_host")
    case("classify: no reuse anywhere is cold", classify_residency(0, 0, 11191), "cold")
    case("classify: a mixed hit above half local reads gpu",
         classify_residency(6000, 5000, 11191), "gpu")
    case("classify: no prompt tokens is no verdict", classify_residency(0, 0, 0), None)
    case("one block of reuse is still cold by the ENG1c gate",
         classify_residency(16, 0, 11191), "cold")

    # the M2 outcome rule, including its indeterminate and no-evidence arms
    def m2_outcome(ct_t: Optional[int], ct_u: Optional[int]) -> str:
        h = [None if c is None else c > COLD_OK_CACHED_MAX for c in (ct_t, ct_u)]
        if h[0] is None or h[1] is None:
            return "NO EVIDENCE"
        if h[0] and not h[1]:
            return "T_SURVIVED"
        if h[1] and not h[0]:
            return "U_SURVIVED"
        return "INDETERMINATE"
    case("M2: touched hits, untouched misses", m2_outcome(11000, 0), "T_SURVIVED")
    case("M2: the reverse is reported as the reverse", m2_outcome(0, 11000), "U_SURVIVED")
    case("M2: both hit is indeterminate, not a pass", m2_outcome(11000, 11000), "INDETERMINATE")
    case("M2: both miss is indeterminate, not a pass", m2_outcome(0, 0), "INDETERMINATE")
    case("M2: an absent usage block is no evidence, not a miss", m2_outcome(None, 0),
         "NO EVIDENCE")
    case("M2: one block of reuse counts as a miss", m2_outcome(16, 0), "INDETERMINATE")

    # the M1 pass rule and its negative control
    def m1_pass(warm_ct: Optional[int], warm_pt: int, cold_ct: Optional[int]) -> bool:
        if warm_ct is None or cold_ct is None or not warm_pt:
            return False
        return (warm_ct / float(warm_pt) >= GPU_CLASSIFY_FRAC
                and cold_ct <= COLD_OK_CACHED_MAX and warm_ct > cold_ct)
    case("M1: warm reuses its history, cold reuses nothing", m1_pass(11100, 11191, 0), True)
    case("M1: a warm arm reusing nothing fails", m1_pass(0, 11191, 0), False)
    case("M1: a cold arm that is not cold fails", m1_pass(11100, 11191, 9000), False)
    case("M1: absent cached_tokens can never pass", m1_pass(None, 11191, None), False)
    case("M1: reuse below the ENG1c gpu threshold fails", m1_pass(5000, 11191, 0), False)

    # the M3 verification gate: both channels must say host
    def m3_ok(twin: Optional[str], timed: Optional[str]) -> bool:
        return twin in ("host", "partial_host") and timed in ("host", "partial_host")
    case("M3: both channels say host", m3_ok("host", "host"), True)
    case("M3: a gpu twin does not verify a host reload", m3_ok("gpu", "host"), False)
    case("M3: a cold timed request does not verify", m3_ok("host", "cold"), False)
    case("M3: no classification at all does not verify", m3_ok(None, None), False)

    case("binomial: 4 of 4 one-sided", _binom_p(4, 4), 0.0625)
    case("binomial: 3 of 4 one-sided", _binom_p(3, 4), 0.3125)

    # the committed cache-key conventions this script leans on
    rt = CK.run_tag(7, "selftest")
    u1 = CK.mm_uuid(rt, "devA", "sess", "sess|f00000.00")
    u2 = CK.mm_uuid(rt, "devB", "sess", "sess|f00000.00")
    case("D84: the same frame under two devices has two mm uuids", u1 != u2, True)
    case("D84: the same frame under one device is stable",
         u1 == CK.mm_uuid(rt, "devA", "sess", "sess|f00000.00"), True)
    case("D84: two devices never share a cache salt",
         CK.cache_salt(rt, "devA") != CK.cache_salt(rt, "devB"), True)
    try:
        CK.check_isolation({"devA": {CK.cache_salt(rt, "devA")},
                            "devB": {CK.cache_salt(rt, "devB")}},
                           {("devA", "f0"): {u1}, ("devB", "f0"): {u2}})
        case("D84: check_isolation accepts a correct run", True, True)
    except AssertionError as ex:                                          # noqa: BLE001
        case("D84: check_isolation accepts a correct run", repr(ex), True)
    try:
        CK.check_isolation({"devA": {"S"}, "devB": {"S"}}, {})
        case("D84: check_isolation rejects a shared salt", "accepted", "raised")
    except AssertionError:
        case("D84: check_isolation rejects a shared salt", "raised", "raised")

    # the metrics flattener against a real-shaped scrape
    flat = _flatten_metrics(
        '# HELP x\n'
        'vllm:prompt_tokens_by_source_total{model_name="32BI",source="local_cache_hit"} 10\n'
        'vllm:prompt_tokens_by_source_total{model_name="32BI",source="external_kv_transfer"} 7\n'
        'vllm:external_prefix_cache_hits_total{model_name="32BI"} 3\n'
        'vllm:request_latency_seconds_bucket{le="1"} 99\n'
        'process_cpu_seconds_total 5\n')
    case("metrics: the source label becomes the key suffix", flat.get(SRC_EXTERNAL), 7.0)
    case("metrics: a bucket series is dropped", any(k.endswith("_bucket") for k in flat), False)
    case("metrics: a non-vllm series is dropped",
         any("process_cpu" in k for k in flat), False)
    case("metrics: delta keeps only what moved",
         mdelta({SRC_LOCAL: 10.0, SRC_EXTERNAL: 7.0}, {SRC_LOCAL: 10.0, SRC_EXTERNAL: 9.0}),
         {SRC_EXTERNAL: 2.0})

    # the committed usage readers, including the None-is-not-zero contract
    case("usage: cached_tokens is read from prompt_tokens_details",
         cached_tokens_of({"prompt_tokens_details": {"cached_tokens": 4940}}), 4940)
    case("usage: an absent field is None, never 0", cached_tokens_of({"prompt_tokens": 10}), None)
    case("usage: no usage block is None", cached_tokens_of({}), None)
    case("usage: an external key is surfaced when present",
         EA.external_cached_tokens_of(
             {"prompt_tokens_details": {EA.EXTERNAL_HIT_KEYS[0]: 123}}), 123)
    case("usage: no external key is None, never 0",
         EA.external_cached_tokens_of({"prompt_tokens_details": {"cached_tokens": 1}}), None)

    return dict(cases=cases, n=len(cases), all_ok=all(c["ok"] for c in cases),
                n_failed=sum(0 if c["ok"] else 1 for c in cases))


# ---------------------------------------------------------------------------- main
EPILOG = """\
EXPECTED WALL CLOCK: 6 to 10 minutes with the defaults, hard-capped by --duration-budget-s
(default 900 s). The cap is checked before every phase and every repetition; a phase that does
not fit is recorded NOT ATTEMPTED (budget) instead of overrunning.

WHAT THE H100 NEEDS RUNNING: the live2 round-1 32B server and nothing else on the GPU.
Qwen3-VL-32B-Instruct @0cfaf481 served as 32BI on 127.0.0.1:8031, vLLM 0.31.0, prefix caching
ON, --enable-prompt-tokens-details, --mm-processor-cache-gb 128, --kv-offloading-backend native
--kv-offloading-size 27 (results/orchestration/live2/pre/live2_pre_server.json). This script
starts no server, installs nothing and writes nothing outside its one result JSON.

A --dry run against experiments/orchestration/live/fake_server.py validates this script's own
logic with no GPU. It MUST report all three measurements NOT ESTABLISHED, because the stub
reports no cached_tokens; a dry run that reports a pass means the script is fabricating one.
"""


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] + "  EXPECTED WALL CLOCK: 6 to 10 min (cap 15 min).",
        epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL,
                    help="the round-1 server, no /v1 suffix (default %(default)s)")
    ap.add_argument("--served-model", default=DEFAULT_SERVED_MODEL,
                    help="--served-model-name of the round-1 server (default %(default)s)")
    ap.add_argument("--dry", action="store_true",
                    help="validate this script's logic against the CPU stub: synthetic frames, "
                         "stub hints left on the wire, and every verdict expected NOT ESTABLISHED")
    ap.add_argument("--duration-budget-s", type=float, default=900.0,
                    help="hard wall-clock cap for the whole run (default %(default)s)")
    ap.add_argument("--frames-per-history", type=int, default=124,
                    help="D2 frames per history; 124 at %d tok/img plus a %d-token header is "
                         "about the committed %d-token nominal history (default %%(default)s)"
                         % (D2_TOK_PER_IMG, D2_HEADER_TOK, S_HIST_TOKENS))
    ap.add_argument("--slice-frames", type=int, default=11,
                    help="frames per warm-ahead piece; 11 at %d tok/img is about the committed "
                         "%d-token slice (default %%(default)s)"
                         % (D2_TOK_PER_IMG, EA.WARM_AHEAD_SLICE_TOKENS))
    ap.add_argument("--m1-reps", type=int, default=3)
    ap.add_argument("--m2-reps", type=int, default=3,
                    help="repetitions PER CONDITION; M2 runs TOUCH and NOTOUCH (default %(default)s)")
    ap.add_argument("--m3-reps", type=int, default=3)
    ap.add_argument("--ladder-units", type=int, default=24,
                    help="sentinel rungs used to MEASURE the eviction frontier; must exceed the "
                         "frontier or the frontier is reported NOT ESTABLISHED (default %(default)s)")
    ap.add_argument("--m3-flood-tokens", type=int, default=0,
                    help="GPU pressure per M3 repetition; 0 means 1.2 x the committed %d-token "
                         "pool (default %%(default)s)" % GPU_POOL_TOKENS)
    ap.add_argument("--frames-dir", default=str(D2_STORE),
                    help="round-1 D2 JPEG store (default %(default)s)")
    ap.add_argument("--frame-manifest", default=str(COMBINED_MANIFEST),
                    help="part-2 JPEG manifest, used when it exists (default %(default)s)")
    ap.add_argument("--max-session-candidates", type=int, default=12,
                    help="how many committed EVAL sessions to try before giving up on frame "
                         "resolution (default %(default)s)")
    ap.add_argument("--session", default=None,
                    help="override the committed EVAL session this confirmation uses")
    ap.add_argument("--dry-time-scale", type=float, default=0.02,
                    help="--dry only: the CPU stub's service-time compression, sent as the stub "
                         "hint fm_time_scale and stripped before any real request (default "
                         "%(default)s)")
    ap.add_argument("--seed", type=int, default=0,
                    help="run seed; it enters the run tag, so every run has its own engine-side "
                         "cache namespace and no run can be served from another's cache")
    ap.add_argument("--out", default=None,
                    help="result JSON (default results/orchestration/live2/v5/"
                         "engine_actions_32b_confirmation.json, or ..._dry.json under --dry)")
    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    global _TIME_SCALE
    if args.dry:
        _TIME_SCALE = float(args.dry_time_scale)
    t_start = time.time()
    budget = Budget(args.duration_budget_s)
    out_path = Path(args.out) if args.out else (
        REPO / ("results/orchestration/live2/v5/engine_actions_32b_confirmation%s.json"
                % ("_dry" if args.dry else "")))

    run_tag = CK.run_tag(int(args.seed), "confirm32b-%d" % int(t_start), label="live2")
    result: Dict[str, Any] = dict(
        study="StudyV5-ENGINE", leg="32B confirmation on the deployment stack",
        version=VERSION, engine_actions_version=EA.ENGINE_ACTIONS_VERSION,
        mode=("DRY: CPU STUB, NOT A MEASUREMENT" if args.dry else "LIVE"),
        register=("MEASURED: TTFT and total seconds, engine-reported prompt and cached tokens, "
                  "and engine metric deltas, on the deployment stack. CONSTRUCTED: the pressure "
                  "traffic, the frame count per history and the slice size. COMMITTED: the "
                  "request bodies (bodies.py), the cache keys (cachekeys.py, D84), the pool sizes "
                  "and the residency classifier (StudyENG1c)."),
        run_tag=run_tag,
        server_requirement=dict(
            which="the live2 round-1 32B server, already running; this script starts nothing",
            model="Qwen3-VL-32B-Instruct @0cfaf481 served as 32BI",
            vllm="0.31.0", base_url=args.base_url, served_model=args.served_model,
            flags_source="results/orchestration/live2/pre/live2_pre_server.json",
            prefix_caching="ON (--enable-prefix-caching, --enable-prompt-tokens-details)",
            kv_offloading="native, 27 GiB (--kv-offloading-backend native "
                          "--kv-offloading-size 27)",
            committed_gpu_kv_tokens=GPU_POOL_TOKENS,
            committed_host_tier_tokens=HOST_CAP_TOKENS,
            max_model_len=MAX_MODEL_LEN),
        caching_statement=(
            "Prefix caching is ON for every request. Every measured row carries a `cache` block "
            "naming its condition (WARM, COLD, or UNKNOWN BY DESIGN where residency is the "
            "measurement), what was cached before it was sent, and whether a repeat could be "
            "served from cache. Warm and cold rows are never compared without the comparison "
            "saying so. The run tag carries the wall clock, so no run of this script can be "
            "served from another run's cache entries."),
        caveats=dict(
            touch_wiring=(
                "`coordinator._enact` handles KEEP_GPU_WARM by setting `SessionRec.desired_tier` "
                "(coordinator.py:482) and emits NO request, so a harness touch cannot move the "
                "engine's own eviction order. M2 confirms the ENGINE property the policy's touch "
                "lever depends on. It does not confirm that the lever as wired reaches the "
                "engine, and must not be cited as if it did."),
            warm_ahead_expressibility=(
                "`interface.validate_action` accepts a MATERIALIZE only for a session that is "
                "already warm or already has a pending question, so warming AHEAD is "
                "unexpressible in the committed action space today "
                "(reports/study_engine_actions.md section 3). M1 shows the engine pays off a "
                "warm-ahead when one is issued; it does not show that an arm can issue one."),
            filler_is_text=(
                "the pressure traffic is text, not frames. It is a proxy for KV OCCUPANCY and "
                "LRU movement only, which is all M2 and M3 ask of it, and is not a proxy for "
                "fleet traffic composition."),
            m3_trigger_state=(
                "the host-resident condition is CREATED here. Across 56 committed 16-device "
                "cells the harness's believed_tier is never host, so M3 speaks to the engine "
                "action's cost and not to how often the policy would reach it.")),
        args=vars(args), out=str(out_path))

    result["selftest"] = selftest()
    e: Optional[Engine] = None
    scratch = Path(tempfile.mkdtemp(prefix="confirm32b-dry-")) if args.dry else out_path.parent
    try:
        if not result["selftest"]["all_ok"]:
            raise Stop("the decision-rule self-test failed (%d of %d cases); the script's own "
                       "logic is wrong and nothing it measures could be trusted."
                       % (result["selftest"]["n_failed"], result["selftest"]["n"]))
        cands = pick_questions(int(args.frames_per_history))
        if args.session:
            cands = [c for c in cands if c["session_id"] == args.session]
            if not cands:
                raise Stop("--session %r is not an EVAL session in the committed split"
                           % args.session)
        question, frames, finfo, tried = None, None, None, []
        if args.dry:
            question = cands[0]
            frames, finfo = dry_frames(question["session_id"], int(args.frames_per_history),
                                       scratch)
        else:
            for c in cands[:int(args.max_session_candidates)]:
                try:
                    frames, finfo = resolve_frames(
                        c["session_id"], c["t_ask"], int(args.frames_per_history),
                        Path(args.frames_dir).expanduser(),
                        Path(args.frame_manifest).expanduser())
                    question = c
                    break
                except Stop as ex:
                    tried.append(dict(session_id=c["session_id"], t_ask=c["t_ask"],
                                      why=str(ex).splitlines()[0]))
            if question is None:
                raise Stop("no committed EVAL session yielded %d resolvable D2 frames in the "
                           "first %d candidates. First few failures: %s\n  Fix one of: point "
                           "--frames-dir at the round-1 store, pass --frame-manifest, lower "
                           "--frames-per-history, or raise --max-session-candidates."
                           % (int(args.frames_per_history), int(args.max_session_candidates),
                              json.dumps(tried[:3])))
        result["question"] = question
        result["session_candidates_tried"] = tried
        result["n_session_candidates"] = len(cands)
        result["frames"] = finfo
        result["frames"]["n_frames"] = len(frames)
        result["frames"]["expected_prompt_tokens"] = D2_HEADER_TOK + D2_TOK_PER_IMG * len(frames)
        result["frames"]["committed_nominal_history_tokens"] = S_HIST_TOKENS

        e = Engine(args.base_url, args.served_model, args.dry)
        result["preflight"] = preflight(e, args, run_tag)
        filler = Filler(e, run_tag, args.served_model, int(args.seed) + 11)
        unit = D2_HEADER_TOK + D2_TOK_PER_IMG * len(frames)

        if not result["preflight"]["ok"] and not args.dry:
            reason = ("the prefix-cache positive control did not pass (%s), so no cached-token "
                      "number from this server can be read and all three measurements are NOT "
                      "ESTABLISHED" % result["preflight"]["positive_control"]["verdict"])
            for k in ("M1", "M2", "M3"):
                result[k] = dict(verdict="NOT ESTABLISHED", established=False, reason=reason)
            result["frontier"] = dict(verdict="NOT ATTEMPTED", reason=reason)
        else:
            if not result["preflight"]["ok"]:
                result["preflight"]["dry_note"] = (
                    "the positive control cannot pass against the CPU stub, which reports no "
                    "cached_tokens. Under --dry the phases run anyway, because the point of a dry "
                    "run is to exercise the plumbing; on a real server a failed control stops "
                    "every measurement.")
            result["M1"] = measure_m1(e, args, run_tag, frames, question, budget)
            result["frontier"] = (calibrate_frontier(e, args, run_tag, unit, budget)
                                  if budget.have(120.0, "frontier calibration")
                                  else dict(verdict="NOT ATTEMPTED (budget)"))
            if args.dry and (result["frontier"].get("verdict") != "MEASURED"):
                # DRY FIXTURE. The CPU stub reports no cached tokens, so the frontier walk
                # cannot find a frontier and M2 and M3 would short-circuit before sending
                # anything. A small synthetic frontier is substituted HERE AND ONLY UNDER --dry
                # so the whole decision path, every body and every probe is exercised on flash.
                # It cannot manufacture a pass: the verdicts below still rest on cached_tokens
                # and on the residency classifier, both of which the stub leaves empty.
                result["frontier"] = dict(
                    result["frontier"], verdict="MEASURED", synthetic_for_dry=True,
                    unit_tokens=unit, frontier_units=4, frontier_tokens=4 * unit,
                    note="DRY FIXTURE, not a measurement: the stub has no prefix cache")
            result["M3"] = measure_m3(e, args, run_tag, frames, question, result["frontier"],
                                      filler, result["preflight"], budget, dry=args.dry)
            result["M2"] = measure_m2(e, args, run_tag, frames, question, result["frontier"],
                                      filler, budget)
        result["metrics_at_end"] = e.metrics()
        result["requests"] = e.rows
        result["n_requests"] = e.n_requests
        result["filler_totals"] = dict(n_requests=filler.n, tokens=filler.tokens_sent,
                                       seconds=round(filler.seconds, 2),
                                       chars_per_token=filler.chars_per_token)
        # D84 on this run's own request bodies, with ONE deliberate exclusion. M3's COLD_KV arm
        # exists precisely to send one device's unchanged mm uuids under a SECOND cache_salt, so
        # that the frames stay in the mm processor cache while the KV prefix chain becomes a new
        # key. That is a second salt on one device, which `check_isolation` rejects by design, so
        # the role is excluded by name and the exclusion is reported rather than hidden. Its mm
        # uuids are still checked; only its salt is.
        excluded = ("timed_cold_kv",)
        try:
            salts: Dict[str, set] = {}
            uf: Dict[Tuple[str, str], set] = {}
            for k in e.keys:
                if k["role"] not in excluded:
                    salts.setdefault(k["device_id"], set()).add(k["salt"])
                for u in k["mm_uuids"]:
                    uf.setdefault((k["device_id"], u.rsplit("|", 1)[-1]), set()).add(u)
            result["d84_isolation"] = CK.check_isolation(salts, uf)
            result["d84_isolation"].update(
                verdict="PASS", excluded_roles=list(excluded),
                exclusion_reason="M3's COLD_KV arm deliberately re-salts one device so the KV "
                                 "prefix chain is new while the mm uuids are not; its salt is "
                                 "therefore not subject to the one-salt-per-device rule. Its "
                                 "uuids are checked.")
        except AssertionError as ex:                                       # noqa: BLE001
            result["d84_isolation"] = dict(verdict="FAIL", error=str(ex),
                                           excluded_roles=list(excluded))
    except Stop as ex:
        result["stopped"] = str(ex)
        if e is not None:
            # A partial run's rows are the only diagnosis the H100 gets, so they are kept.
            result.setdefault("requests", e.rows)
            result.setdefault("n_requests", e.n_requests)
        for k in ("M1", "M2", "M3"):
            result.setdefault(k, dict(verdict="NOT ESTABLISHED", established=False,
                                      reason="the run stopped before this measurement: %s" % ex))
    finally:
        if args.dry:
            import shutil
            shutil.rmtree(scratch, ignore_errors=True)

    established = {k: bool(result.get(k, {}).get("established")) for k in ("M1", "M2", "M3")}
    result["headline"] = dict(
        established=established,
        all_three=all(established.values()),
        verdicts={k: result.get(k, {}).get("verdict") for k in ("M1", "M2", "M3")},
        statement=("32B CONFIRMATION PASSED: all three engine actions hold on the deployment stack"
                   if all(established.values()) else
                   "32B CONFIRMATION NOT PASSED: " + "; ".join(
                       "%s %s" % (k, result.get(k, {}).get("verdict")) for k in ("M1", "M2", "M3")
                       if not established[k])),
        policy_consequence=("reload may go live" if established["M3"] else
                            "policy v5 may still go live with RELOAD DISABLED and marked "
                            "PROVISIONAL (the user's standing ruling on this row)"))
    result["budget"] = dict(limit_s=args.duration_budget_s, spent_s=round(budget.spent, 2),
                            skipped=budget.notes)
    if args.dry:
        dry_clean = (not any(established.values()))
        result["dry_validation"] = dict(
            expected="all three NOT ESTABLISHED, because the CPU stub reports no cached_tokens, "
                     "models no prefix cache and exposes no offload counters",
            selftest_all_ok=result["selftest"]["all_ok"],
            no_fabricated_pass=dry_clean,
            verdict=("PASS: the plumbing ran end to end and the script refused to conclude"
                     if dry_clean and result["selftest"]["all_ok"] else
                     "FAIL: a dry run must not report any measurement established"))
    try:
        import _provenance
        result["_provenance"] = _provenance.stamp(
            script=SCRIPT, model=("none-cpu-stub" if args.dry else "qwen3vl32b"),
            device=("nvidia_rtx_a6000" if args.dry else "h100nvl"),
            n=result.get("n_requests", 0), seed=int(args.seed), args=args)
    except Exception as ex:                                                # noqa: BLE001
        result["_provenance"] = dict(git_commit="unstamped", script=SCRIPT,
                                     note="stamp failed: %r" % (ex,))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps(dict(headline=result["headline"], budget=result["budget"],
                          preflight=result.get("preflight", {}).get("positive_control"),
                          frontier={k: v for k, v in (result.get("frontier") or {}).items()
                                    if k != "probes"},
                          dry_validation=result.get("dry_validation"),
                          stopped=result.get("stopped")), indent=2, default=str))
    print("wrote", out_path)
    if result.get("stopped"):
        return 2
    if args.dry:
        return 0 if result["dry_validation"]["verdict"].startswith("PASS") else 1
    return 0 if result["headline"]["all_three"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
