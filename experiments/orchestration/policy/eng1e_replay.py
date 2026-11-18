"""StudyENG1e-chain's per-step request membership, loaded for StudyPOL6 Part B.

WHAT StudyENG1e MEASURES AND WHY POL6 NEEDS IT. StudyPOL6 Part A localized the frozen model's
over-prediction of a chained rebuild's imposed delay to background requests whose first token
lands WHILE a piece is prefilling (89 % of 303.9 s over 161 ENG1c Part D FIT trials), and its
leading explanation is that pol4 models a piece as one long step while the engine really spreads
it over about 1.8 shorter ones and co-batches background prefill into them. Part A could only
DERIVE that composition by subtracting the action's own computed tokens from each step's
first-output tokens, because StudyENG1c does not record which requests were in which step.
StudyENG1e-chain records it directly, which is the one measurement that can turn the
explanation into model parameters (`pol6_engine.AWAITING_ENG1E`).

STATUS: ADAPTED TO THE COMMITTED SCHEMA (StudyPOL6 Part B, 2026-11-17). StudyENG1e-chain is
committed (COMPLETE, h100nvl GPU 2) and its report section 1.1 fixes the step-row schema. The
declared requirement below was written BEFORE the schema was seen and is kept verbatim; what
changed is an ADAPTER, not the requirement:

  * committed step row: {i, t0, el, t1, ts, tr, r} with `r` a list of
    [engine request id, scheduled tokens, "p" or "d", computed tokens before the step,
    encoder inputs]. `COMMITTED_STEP_FIELDS` records it and `adapt_step_row()` maps it onto
    the declared shape, so `REQUIRED_STEP_FIELDS` still describes what Part B consumes.
  * STEP TIMING follows the report, not `el` alone: end = t0 + el, start = max(ts, previous
    end). The report measured a mono first step whose `el` was 0.025 ms after a 1.64 s
    execute_model call, so `el` does NOT bound a step that blocks on the CPU side. This is the
    ENG1e analogue of the `elapsed_ms` trap Part A already hit on ENG1c.
  * the holdout fence now works on the REAL split file (5 of 20 trials per (load, action), the
    same trials in both injection modes) and on the per-request rows' own `holdout` flag.
  * `ENG1E_ROOT` may be overridden so the files can be read from a scratch root when the branch
    cannot be fast-forwarded; the provenance of every file read is recorded by md5.
"""
from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ENG1E_DIR = "results/cost/study_eng1e"
ENG1E_SPLIT_PATH = "results/cost/study_eng1e/eng1e_holdout_split.json"
ENG1E_REPORT_PATH = "reports/study_eng1e_chain.md"

# What Part B needs from a step row, declared before the schema is seen.
REQUIRED_STEP_FIELDS = ("t", "step", "members")
# What Part B needs about each request inside a step.
REQUIRED_MEMBER_FIELDS = ("rid", "new_tokens")
# Optional, used where present: images in the step, the member's cached tokens, the step's
# wall duration, and whether the member was decoding rather than prefilling.
OPTIONAL_MEMBER_FIELDS = ("cached_tokens", "images", "decoding")


class HoldoutFenced(PermissionError):
    """Raised when StudyENG1e's HOLDOUT rows are requested without authorization."""


class SchemaNotCommitted(FileNotFoundError):
    """Raised when StudyENG1e's own files are asked for before the study is committed."""


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def eng1e_is_committed(root: Optional[Path] = None) -> bool:
    r = root or _root()
    return (r / ENG1E_SPLIT_PATH).exists() and (r / ENG1E_REPORT_PATH).exists()


@dataclass
class StepMembership:
    """One engine step with the requests that were in it, as StudyENG1e measures them."""

    t: float
    step: int
    members: List[Dict[str, Any]]
    dur_s: Optional[float] = None
    holdout: bool = False
    trial: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def prefilling(self) -> List[Dict[str, Any]]:
        return [m for m in self.members if not m.get("decoding")
                and int(m.get("new_tokens", 0) or 0) > 0]

    def decoding(self) -> List[Dict[str, Any]]:
        return [m for m in self.members if m.get("decoding")]

    def n_prefilling(self) -> int:
        return len(self.prefilling())

    def other_prefill_tokens(self, rid: str) -> int:
        """The measured, not derived, count Part A had to obtain by subtraction."""
        return sum(int(m.get("new_tokens", 0) or 0) for m in self.prefilling()
                   if str(m.get("rid")) != str(rid))

    def shares_with_background(self, action_rids: Sequence[str]) -> bool:
        acts = {str(r) for r in action_rids}
        return any(str(m.get("rid")) not in acts for m in self.members)


def _check_row(row: Dict[str, Any], where: str) -> None:
    missing = [f for f in REQUIRED_STEP_FIELDS if f not in row]
    if missing:
        raise ValueError(
            "%s: a StudyENG1e step row is missing %s. StudyPOL6 Part B declared the fields it "
            "needs in eng1e_replay.REQUIRED_STEP_FIELDS before the schema was committed; if "
            "StudyENG1e named them differently, add an adapter rather than relaxing this check."
            % (where, missing))
    if not isinstance(row["members"], list):
        raise ValueError("%s: `members` must be a list of per-request records" % where)
    for m in row["members"]:
        bad = [f for f in REQUIRED_MEMBER_FIELDS if f not in m]
        if bad:
            raise ValueError("%s: a step member is missing %s" % (where, bad))


def parse_rows(rows: Iterable[Dict[str, Any]], split: str = "fit",
               authorization: str = "", where: str = "<rows>") -> Tuple[List[StepMembership],
                                                                       Dict[str, Any]]:
    """Every step row of the requested split, with the holdout fence applied.

    The fence is applied BEFORE any row of the other split is turned into a `StepMembership`, so
    a refused read has not constructed a holdout object at all."""
    split = str(split).lower()
    if split not in ("fit", "holdout"):
        raise ValueError("split must be 'fit' or 'holdout', got %r" % split)
    if split == "holdout" and not authorization:
        raise HoldoutFenced(
            "StudyENG1e's HOLDOUT rows are the fresh data StudyPOL6's one-shot is reserved for. "
            "Reading them needs the user's authorization recorded in `authorization`, and the "
            "run itself must go through the T0b one-shot harness so the freeze is re-verified "
            "and a second run is refused.")
    want = (split == "holdout")
    out: List[StepMembership] = []
    seen = dict(rows=0, fit=0, holdout=0, members=0)
    for row in rows:
        seen["rows"] += 1
        hold = bool(row.get("holdout"))
        seen["holdout" if hold else "fit"] += 1
        if hold != want:
            continue
        _check_row(row, where)
        seen["members"] += len(row["members"])
        out.append(StepMembership(
            t=float(row["t"]), step=int(row["step"]), members=list(row["members"]),
            dur_s=(float(row["dur_s"]) if row.get("dur_s") is not None else None),
            holdout=hold, trial=(str(row["trial"]) if row.get("trial") is not None else None),
            raw=row))
    out.sort(key=lambda s: (s.trial or "", s.t, s.step))
    audit = dict(split=split, source=where, n_steps=len(out), rows_read=seen["rows"],
                 n_fit_rows=seen["fit"], n_holdout_rows=seen["holdout"],
                 n_members=seen["members"], authorization=authorization,
                 holdout_steps_built=(len(out) if want else 0),
                 assertions=["no step of the other split is constructed at all",
                             "every step row carries the declared required fields"])
    assert all(s.holdout == want for s in out), "a step of the other split was constructed"
    return out, audit


def read_jsonl(path: Any) -> List[Dict[str, Any]]:
    p = Path(path)
    op = gzip.open if p.suffix == ".gz" else open
    with op(p, "rt") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def load_membership(split: str = "fit", authorization: str = "",
                    path: Any = None) -> Tuple[List[StepMembership], Dict[str, Any]]:
    """StudyENG1e's committed membership rows, or an explicit file.

    With no `path` this refuses until StudyENG1e is committed, rather than guessing a filename
    that the report has not fixed yet."""
    if path is None:
        if not eng1e_is_committed():
            raise SchemaNotCommitted(
                "StudyENG1e-chain is not committed yet: %s and %s must both exist before this "
                "loader can pick its own input. Pass `path` explicitly to parse a file, which "
                "is what the synthetic-example tests do."
                % (ENG1E_SPLIT_PATH, ENG1E_REPORT_PATH))
        raise SchemaNotCommitted(
            "StudyENG1e-chain is committed but this loader has not been pointed at its files. "
            "Check its report's field names against REQUIRED_STEP_FIELDS, set the input path, "
            "and add an adapter for any renamed field.")
    rows = read_jsonl(path)
    return parse_rows(rows, split=split, authorization=authorization, where=str(path))


def steps_per_request(steps: Sequence[StepMembership]) -> Dict[str, int]:
    """The quantity Part A had to derive: how many steps each request's prefill spanned."""
    out: Dict[str, int] = {}
    for s in steps:
        for m in s.prefilling():
            rid = str(m.get("rid"))
            out[rid] = out.get(rid, 0) + 1
    return out


def merge_rate(steps: Sequence[StepMembership], action_rids: Sequence[str]) -> Dict[str, Any]:
    """How often a step that an action was prefilling in also carried someone else's prefill.

    This is the direct measurement of H-merge. Part A estimated it by subtraction on StudyENG1c
    and got a median 3,780 other prefill tokens inside a piece1024 chain's own steps."""
    acts = {str(r) for r in action_rids}
    n_action_steps = 0
    n_shared = 0
    other_tokens = 0
    for s in steps:
        pre = s.prefilling()
        mine = [m for m in pre if str(m.get("rid")) in acts]
        if not mine:
            continue
        n_action_steps += 1
        others = [m for m in pre if str(m.get("rid")) not in acts]
        if others:
            n_shared += 1
            other_tokens += sum(int(m.get("new_tokens", 0) or 0) for m in others)
    return dict(n_action_steps=n_action_steps, n_shared_steps=n_shared,
                shared_fraction=(n_shared / n_action_steps if n_action_steps else None),
                other_prefill_tokens=other_tokens, measured=True,
                note="MEASURED per-step membership, not derived by subtraction as in Part A")


# --------------------------------------------------------------------------- committed schema
#
# StudyENG1e-chain report section 1.1. One row per engine step that scheduled at least one
# token, plus one `init` row. Recorded here so a later rename is caught by a test rather than
# silently adapted away.
COMMITTED_STEP_FIELDS = ("i", "t0", "el", "t1", "ts", "tr", "r")
# r = [engine request id, scheduled tokens, "p" or "d", computed tokens before the step,
#      encoder inputs]
COMMITTED_MEMBER_POSITIONS = ("rid", "sched_tokens", "phase", "computed_before", "enc_inputs")

ENG1E_REQUESTS = "eng1e_requests_h100nvl.jsonl.gz"
ENG1E_RESULTS = "eng1e_results.json"
ENG1E_STEPS = "eng1e_steps_%s.jsonl.gz"          # server tag, e.g. B_P40
ENG1E_MODES = ("B", "A")
ENG1E_LOADS = ("P25", "P40", "S2", "S4")
ENG1E_ACTIONS = ("mono", "chain2048", "chain1024")

# Overridable so the files can be read from a scratch root (see the module docstring).
ENG1E_ROOT: Optional[Path] = None


def eng1e_root() -> Path:
    return Path(ENG1E_ROOT) if ENG1E_ROOT is not None else _root()


def eng1e_path(name: str) -> Path:
    return eng1e_root() / ENG1E_DIR / name


def file_provenance(paths: Iterable[Any]) -> List[Dict[str, Any]]:
    """md5 and size of every input read, so a scratch-root read stays checkable."""
    import hashlib
    out = []
    for p in paths:
        p = Path(p)
        h = hashlib.md5(p.read_bytes()).hexdigest() if p.exists() else None
        out.append(dict(path=str(p), exists=p.exists(),
                        bytes=(p.stat().st_size if p.exists() else None), md5=h))
    return out


def adapt_step_row(row: Dict[str, Any], prev_end: Optional[float] = None) -> Dict[str, Any]:
    """The committed row, mapped onto the shape `REQUIRED_STEP_FIELDS` declares.

    Step timing is the report's rule, NOT `el` alone: end = t0 + el, start = max(ts, prev end).
    `el` understates any step whose execute_model call blocked on the CPU side."""
    missing = [f for f in COMMITTED_STEP_FIELDS if f not in row]
    if missing:
        raise ValueError(
            "a StudyENG1e step row is missing %s; its report section 1.1 fixes the schema as %s. "
            "Add an adapter rather than relaxing the check." % (missing, list(COMMITTED_STEP_FIELDS)))
    end = float(row["t0"]) + float(row["el"]) / 1000.0
    start = float(row["ts"])
    if prev_end is not None:
        start = max(start, float(prev_end))
    members = []
    for m in row["r"]:
        rid, sched, phase, before, enc = (list(m) + [None] * 5)[:5]
        members.append(dict(rid=str(rid), new_tokens=int(sched or 0),
                            decoding=(str(phase) == "d"),
                            computed_before=int(before or 0),
                            enc_inputs=int(enc or 0)))
    return dict(t=start, step=int(row["i"]), members=members,
                dur_s=max(end - start, 0.0), t_end=end, el_ms=float(row["el"]),
                ts=float(row["ts"]), tr=float(row["tr"]), holdout=False)


def load_steps(server: str) -> Tuple[List[StepMembership], Dict[str, Any]]:
    """Every step of one ENG1e server (e.g. "B_P40"), adapted and time-ordered.

    The step log is PER SERVER, not per trial, so it carries FIT and HOLDOUT trials' steps in
    one file. It is therefore loaded WITHOUT a split and the caller must restrict it to the
    request ids of the trials it is allowed to look at; `steps_for_rids` does that."""
    p = eng1e_path(ENG1E_STEPS % server)
    rows = [r for r in read_jsonl(p) if not r.get("init")]
    rows.sort(key=lambda r: int(r["i"]))
    out, prev_end = [], None
    for r in rows:
        a = adapt_step_row(r, prev_end)
        prev_end = a["t_end"]
        out.append(StepMembership(t=a["t"], step=a["step"], members=a["members"],
                                  dur_s=a["dur_s"], holdout=False, trial=server, raw=a))
    return out, dict(server=server, n_steps=len(out), source=str(p),
                     provenance=file_provenance([p]),
                     note="per-server log; restrict to allowed request ids before use")


def engine_rid_prefix(client_rid: str) -> str:
    """The engine id is "chatcmpl-" + client request id + "-" + 8 hex (report section 1.1)."""
    return "chatcmpl-%s-" % client_rid


def steps_for_rids(steps: Sequence[StepMembership],
                   client_rids: Sequence[str]) -> List[StepMembership]:
    """Only the steps that scheduled one of the given client requests."""
    pref = tuple(engine_rid_prefix(r) for r in client_rids)
    out = []
    for s in steps:
        if any(str(m["rid"]).startswith(pref) for m in s.members):
            out.append(s)
    return out


def holdout_split(strict: bool = True) -> Dict[str, Any]:
    """The committed split: 5 of 20 trials per (load, action), the same in both modes."""
    p = eng1e_root() / ENG1E_SPLIT_PATH
    if not p.exists():
        raise SchemaNotCommitted("StudyENG1e's split file is not at %s" % p)
    raw = json.loads(p.read_text())
    hold = {k: sorted(int(x) for x in v) for k, v in raw["holdout"].items()}
    if strict:
        bad = {k: v for k, v in hold.items() if len(v) != 5}
        if bad:
            raise ValueError("the split file must reserve 5 trials per cell; got %s" % bad)
    return dict(raw=raw, holdout=hold, n_cells=len(hold),
                n_holdout_trials=sum(len(v) for v in hold.values()),
                provenance=file_provenance([p]))


def load_eng1e_trials(split: str = "fit", authorization: str = "",
                      path: Any = None) -> Tuple[List[Any], Dict[str, Any]]:
    """Every ENG1e pair of the requested split, as trials the frozen replay can score.

    `load` carries the INJECTION MODE as well as the background load, so criterion (ii)'s
    background condition is (mode, load): the two modes are never pooled (StudyENG1e user
    decision 8), and a trial is never FIT in one mode and HOLDOUT in the other (its split file).
    """
    from . import trace_replay as tr  # local import: keeps the stub importable standalone
    split = str(split).lower()
    if split not in ("fit", "holdout"):
        raise ValueError("split must be 'fit' or 'holdout', got %r" % split)
    if split == "holdout" and not authorization:
        raise HoldoutFenced(
            "StudyENG1e's HOLDOUT trials (5 of 20 per load and action, the same trials in both "
            "injection modes) are the fresh data StudyPOL6's one-shot is reserved for. Reading "
            "them needs the user's authorization recorded in `authorization`, and the run must "
            "go through the T0b one-shot harness so the freeze is re-verified and a second run "
            "is refused.")
    want = (split == "holdout")
    p = Path(path) if path is not None else eng1e_path(ENG1E_REQUESTS)
    buckets: Dict[Tuple[str, str, str, int], Any] = {}
    seen = dict(rows=0, fit_trials=set(), holdout_trials=set(), kinds={}, arms={})
    for row in read_jsonl(p):
        seen["rows"] += 1
        kind = str(row.get("kind"))
        seen["kinds"][kind] = seen["kinds"].get(kind, 0) + 1
        if kind in ("pair_check", "run_summary", "setup_hist", "setup_flush"):
            continue
        arm = row.get("arm")
        if arm not in ("with", "without", "repeat"):
            continue
        hold = bool(row.get("holdout"))
        key = (str(row["mode"]), str(row["load"]), str(row["action"]), int(row["trial"]))
        (seen["holdout_trials"] if hold else seen["fit_trials"]).add(key)
        if hold != want:
            continue
        seen["arms"][arm] = seen["arms"].get(arm, 0) + 1
        t = buckets.get(key)
        if t is None:
            t = tr.Trial(load="%s_%s" % (key[0], key[1]), action=key[2], trial=key[3],
                         holdout=hold, t_inj_rel=float(row.get("t_inj_rel") or 0.0))
            buckets[key] = t
        a = t.arms.get(arm)
        if a is None:
            a = tr.Arm(mode=arm, t0_trace=0.0)
            t.arms[arm] = a
        if kind == "episodic":
            a.background.append(row)
        elif kind == "inject":
            a.action.append(row)
        elif kind == "job":
            setattr(t, "job_record_%s" % arm, row)
    # t0 of each arm is its own earliest submission, as ENG1c's loader does by recording t0_trace
    for t in buckets.values():
        for a in t.arms.values():
            subs = [float(r["t_submit"]) for r in (a.background + a.action)]
            a.t0_trace = min(subs) if subs else 0.0
    trials = [buckets[k] for k in sorted(buckets)]
    sp = holdout_split()
    audit = dict(
        split=split, n_trials=len(trials), source=str(p),
        n_fit_trials_in_record=len(seen["fit_trials"]),
        n_holdout_trials_in_record=len(seen["holdout_trials"]),
        n_holdout_trials_in_split_file=sp["n_holdout_trials"] * len(ENG1E_MODES),
        holdout_trials_built=(len(trials) if want else 0),
        rows_read=seen["rows"], kinds=dict(sorted(seen["kinds"].items())),
        arms=dict(sorted(seen["arms"].items())), authorization=authorization,
        provenance=file_provenance([p, eng1e_root() / ENG1E_SPLIT_PATH]),
        assertions=["the record's holdout flag selects exactly the split file's trial count, "
                    "counted over both injection modes",
                    "no trial of the other split is constructed at all",
                    "every scored trial carries a with arm and a without arm"])
    assert len(seen["holdout_trials"]) == sp["n_holdout_trials"] * len(ENG1E_MODES), (
        "the record flags %d holdout trials, the split file lists %d over %d modes"
        % (len(seen["holdout_trials"]), sp["n_holdout_trials"], len(ENG1E_MODES)))
    if not want:
        assert all(not t.holdout for t in trials), "a holdout trial reached the FIT set"
    missing = [t.key() for t in trials if "with" not in t.arms or "without" not in t.arms]
    assert not missing, "trials without both arms: %s" % missing[:5]
    return trials, audit
