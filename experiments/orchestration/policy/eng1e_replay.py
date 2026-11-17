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

STATUS: STUB, AND DELIBERATELY SO. StudyENG1e is still collecting on the H100 and its report is
not committed, so its on-disk schema is not yet fixed. This module therefore:

  * states the fields Part B needs as `REQUIRED_STEP_FIELDS` and `REQUIRED_MEMBER_FIELDS`, so
    the requirement is on record BEFORE the schema is seen and cannot be quietly reshaped to
    whatever arrives;
  * parses any row set that carries those fields, which the synthetic example in the tests
    exercises end to end;
  * refuses to read StudyENG1e HOLDOUT rows without an explicit authorization string, the same
    fence StudyENG1c Part D and StudyENG1d use;
  * refuses to guess. `load_membership()` with no explicit path raises `SchemaNotCommitted`
    until the report and the split file exist, rather than inventing a filename.

WHEN ENG1e IS COMMITTED. Point `ENG1E_DIR` and `ENG1E_SPLIT_PATH` at the committed files, check
the field names in its report against `REQUIRED_STEP_FIELDS`, add an adapter for any renamed
field, and the holdout fence and the tests carry over unchanged.
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
