"""Spec 5.2 and 11, test T0: does the rollout's prediction match live measurement?

THIS HARNESS MUST NOT BE RUN ON HOLDOUT DATA. T0 is a model-fidelity check, so running it on the
held-out evaluation traces would burn them: every residual it reports is information about those
traces, and a model corrected against them is fitted on them. `T0Harness.run` therefore REFUSES a
dataset whose `split` is not one of the permitted development splits, and the refusal is not
overridable by a keyword argument.

What it compares, per spec 5.2:
  1. the DELAY the candidate action imposes on other requests, predicted against measured;
  2. the predicted COMPLETION TIME of each historical job, predicted against measured;
and it reports the residual distribution per condition with a stated tolerance, plus the
in-sample flag the engine model attached to each prediction.

THE ONE-SHOT HOLDOUT MODE (StudyPOL3-update / StudyT0-fidelity, 2026-11-16). The refusal above
stays the default and `run` is unchanged. A SINGLE run on the held-out Part C triples was
explicitly authorized by the user, and `run_holdout_once` is the only way to take it. It is
fenced three ways:

  1. it REQUIRES a `FrozenState`: the git hash of the working tree and an md5 of every model and
     parameter file the prediction used, recorded BEFORE the run and re-verified at the moment of
     the run, so a model edited after the freeze cannot be the one that was tested;
  2. it APPENDS a log line with the timestamp and those hashes to a one-shot log beside the
     result, so the run leaves a trace that is not the result file;
  3. it REFUSES a second run once a result file for that holdout exists. Deleting the result to
     run again is a visible act in git, which is the point.
"""
from __future__ import annotations

import getpass
import hashlib
import json
import os
import socket
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

PERMITTED_SPLITS = ("dev", "DEV", "train", "TRAIN", "synthetic", "SYNTHETIC",
                    "crossfit-train")
REFUSED_SPLITS = ("holdout", "HOLDOUT", "eval", "EVAL", "test", "TEST")


class HoldoutRefused(PermissionError):
    """Raised when T0 is pointed at data it must not see."""


class FreezeViolation(PermissionError):
    """Raised when the one-shot holdout run cannot prove it is running the frozen model."""


def md5_of(path: Any) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_state(repo: Any) -> Dict[str, Any]:
    """The working tree's state, read-only. A dirty tree is RECORDED, never corrected: the point
    is to say exactly what was run, and `git status --porcelain` is the honest answer."""
    repo = str(repo)

    def _run(args: Sequence[str]) -> str:
        return subprocess.run(list(args), cwd=repo, capture_output=True, text=True,
                              check=False).stdout.strip()

    return dict(head=_run(["git", "rev-parse", "HEAD"]),
                branch=_run(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
                porcelain=_run(["git", "status", "--porcelain"]),
                clean=(_run(["git", "status", "--porcelain"]) == ""))


@dataclass
class FrozenState:
    """The frozen record the one-shot holdout run must match.

    `files` maps a repository-relative path to its md5 at freeze time: every model file, every
    parameter file and every source module whose code produced the prediction."""

    repo: str
    git: Dict[str, Any]
    files: Dict[str, str]
    frozen_at: str
    note: str = ""

    @classmethod
    def freeze(cls, repo: Any, paths: Sequence[str], note: str = "") -> "FrozenState":
        repo = Path(repo)
        files = {}
        for rel in sorted(set(paths)):
            p = repo / rel
            if not p.is_file():
                raise FreezeViolation("cannot freeze %s: it is not a file" % rel)
            files[rel] = md5_of(p)
        return cls(repo=str(repo), git=git_state(repo), files=files,
                   frozen_at=datetime.now(timezone.utc).isoformat(), note=note)

    def verify(self) -> Dict[str, Any]:
        repo = Path(self.repo)
        changed = []
        for rel, h in sorted(self.files.items()):
            p = repo / rel
            if not p.is_file():
                changed.append(dict(path=rel, reason="missing at run time"))
                continue
            now = md5_of(p)
            if now != h:
                changed.append(dict(path=rel, frozen_md5=h, now_md5=now))
        now_git = git_state(repo)
        return dict(ok=not changed and now_git["head"] == self.git["head"],
                    changed=changed, git_frozen=self.git, git_now=now_git)

    def as_dict(self) -> Dict[str, Any]:
        return dict(repo=self.repo, git=self.git, files=dict(self.files),
                    frozen_at=self.frozen_at, note=self.note)


@dataclass
class T0Case:
    case_id: str
    condition: str
    predicted_delay_s: float
    measured_delay_s: float
    predicted_completion_s: Optional[float] = None
    measured_completion_s: Optional[float] = None
    in_sample: bool = True


@dataclass
class T0Harness:
    tolerance_delay_s: float = 0.05
    tolerance_completion_s: float = 0.25
    cases: List[T0Case] = field(default_factory=list)

    def add(self, case: T0Case) -> None:
        self.cases.append(case)

    def run(self, dataset: Dict[str, Any]) -> Dict[str, Any]:
        split = str(dataset.get("split", "")).strip()
        if split in REFUSED_SPLITS or split.lower() in ("holdout", "eval", "test"):
            raise HoldoutRefused(
                "T0 is a cost-model fidelity check and must not be run on %r: fitting the engine "
                "model against held-out traces makes every later comparison in-sample. Spec 5.2 "
                "and CLAUDE.md both forbid it." % split)
        if split not in PERMITTED_SPLITS:
            raise HoldoutRefused(
                "refusing an unrecognized split %r; name it explicitly as one of %s so the "
                "provenance of a T0 result is never in doubt" % (split, list(PERMITTED_SPLITS)))
        cases = [T0Case(**c) if isinstance(c, dict) else c for c in dataset.get("cases", [])]
        cases = list(self.cases) + cases
        if not cases:
            return dict(split=split, n=0, verdict="NO CASES", note="T0 has not been run")
        by_cond: Dict[str, List[T0Case]] = {}
        for c in cases:
            by_cond.setdefault(c.condition, []).append(c)
        rows = []
        for cond, cs in sorted(by_cond.items()):
            dres = [c.predicted_delay_s - c.measured_delay_s for c in cs]
            cres = [c.predicted_completion_s - c.measured_completion_s for c in cs
                    if c.predicted_completion_s is not None
                    and c.measured_completion_s is not None]
            rows.append(dict(
                condition=cond, n=len(cs),
                delay_residual=_dist(dres), completion_residual=_dist(cres),
                within_delay_tolerance=all(abs(x) <= self.tolerance_delay_s for x in dres),
                within_completion_tolerance=all(abs(x) <= self.tolerance_completion_s
                                                for x in cres) if cres else None,
                n_out_of_sample=sum(1 for c in cs if not c.in_sample)))
        passed = all(r["within_delay_tolerance"] and
                     (r["within_completion_tolerance"] in (True, None)) for r in rows)
        return dict(
            split=split, n=len(cases), per_condition=rows,
            tolerance_delay_s=self.tolerance_delay_s,
            tolerance_completion_s=self.tolerance_completion_s,
            verdict=("PASS" if passed else "FAIL"),
            note=("a PASS on a SYNTHETIC dataset establishes only that the harness computes what "
                  "it claims; T0 is established by live measurement on the H100 (spec 11)"))


    def run_holdout_once(self, frozen: FrozenState, result_path: Any, log_path: Any,
                         compute, split_name: str = "holdout",
                         authorization: str = "") -> Dict[str, Any]:
        """The ONE authorized run on the held-out Part C triples.

        `compute` is a zero-argument callable that produces the result dict. It is called ONLY
        after the freeze verifies and the result file is confirmed absent, so a refused run never
        touches the holdout at all."""
        if not authorization:
            raise HoldoutRefused(
                "run_holdout_once needs the user's authorization recorded in `authorization`; "
                "T0 on the holdout is a one-shot test and the record must say who authorized it")
        result_path = Path(result_path)
        log_path = Path(log_path)
        if result_path.exists():
            raise HoldoutRefused(
                "a holdout result already exists at %s. T0 on this holdout is ONE-SHOT: a "
                "second run would be a model corrected against the held-out traces, which makes "
                "every later comparison in-sample. Removing that file to run again is a visible "
                "act in git, which is the point." % result_path)
        v = frozen.verify()
        if not v["ok"]:
            raise FreezeViolation(
                "the frozen state does not match the working tree, so this run would not be a "
                "test of the frozen model: %s" % json.dumps(
                    dict(changed=v["changed"], git_frozen=v["git_frozen"]["head"],
                         git_now=v["git_now"]["head"])))
        started = datetime.now(timezone.utc).isoformat()
        out = compute()
        finished = datetime.now(timezone.utc).isoformat()
        rec = dict(event="t0_holdout_one_shot", split=split_name, started_utc=started,
                   finished_utc=finished, authorization=authorization,
                   git_head=frozen.git["head"], git_clean=frozen.git["clean"],
                   frozen_at=frozen.frozen_at, file_md5=dict(frozen.files),
                   result_path=str(result_path),
                   host=socket.gethostname(), user=getpass.getuser(), pid=os.getpid())
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
        out = dict(out)
        out["_one_shot"] = rec
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(out, indent=1, default=str))
        return out


def _dist(xs: Sequence[float]) -> Optional[Dict[str, float]]:
    if not xs:
        return None
    ys = sorted(xs)
    n = len(ys)
    def q(p: float) -> float:
        pos = (n - 1) * p
        lo = int(pos)
        hi = min(lo + 1, n - 1)
        return ys[lo] * (1 - (pos - lo)) + ys[hi] * (pos - lo)
    return dict(n=n, mean=sum(ys) / n, p50=q(0.5), p05=q(0.05), p95=q(0.95), min=ys[0],
                max=ys[-1], max_abs=max(abs(ys[0]), abs(ys[-1])))


def synthetic_dataset(ro, fleet, items, measured_overhead_s: float = 0.0) -> Dict[str, Any]:
    """A replay the harness can be exercised on without any live run: the rollout predicts the
    delay each release imposes, and the 'measurement' is the same engine model plus a stated
    constant overhead. It proves the plumbing, not the engine model, and says so."""
    from .rollout import delta_j
    cases = []
    for it in items:
        res = delta_j(ro, fleet, dict(kind="release", item_id=it.item_id))
        pred = res["engine_busy_delta_s"]
        cases.append(dict(case_id=it.item_id, condition=it.kind,
                          predicted_delay_s=pred,
                          measured_delay_s=pred + measured_overhead_s,
                          in_sample=res["in_sample"]))
    return dict(split="synthetic", cases=cases,
                note="SYNTHETIC: the 'measurement' is the model itself plus %.3f s, so this "
                     "exercises the harness and NOT the engine model" % measured_overhead_s)
