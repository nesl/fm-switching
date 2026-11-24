#!/usr/bin/env python3
"""Torn-tree guard (H100 2026-11-24, after the eco-llm 1x s5 incident): did the runner and its
coordinator child run the same code, and did the tree move under the cell?

WHAT HAPPENED. A rebase landed flash's a43ad7f into the working tree while a split cell was starting.
The runner had loaded the old `run_live2_real.py` (no `context_limit_tokens` in cfg); the coordinator
child imported the new `procsplit` / `context_limit` and raised. That time a fail-loud happened to sit
on the seam. This module makes the check general.

THREE CASES, each recorded by name, never merged:
  1. `runner_child_mismatch`: a file BOTH the runner and the child loaded hashes differently in the
     two maps -> `TornTree` at child start, before the cell runs.
  2. `moved_after_import`: a module the child had ALREADY loaded at start whose file differs at end.
     Python caches an imported module, so the change never executed -> WARNING, the cell is kept.
  3. `torn_lazy_import`: a module FIRST loaded after start whose file at end differs from its START
     hash, i.e. the new bytes may have executed beside old ones -> INVALID.
Case 3 is a pure hash comparison because the child hashes EVERY .py under experiments/orchestration
at start, not only what it has loaded, so a late import always has a start hash. No mtime anywhere:
mtime is preserved by content-changing copies (cp -p, rsync --times) and moved by content-preserving
ones (touch, an identical rewrite), so it fails in both directions.

WHAT A HASH HERE MEANS: sha256 of the FILE ON DISK. It answers "did the tree move under the cell",
not "what bytecode executed".

STATED BOUNDS, so a pass is not read as stronger than it is:
  - A file changed and changed back within one cell is invisible.
  - RUNNER-ONLY files (e.g. run_live2_real.py itself) are outside the runner/child overlap, so a
    rebase touching only them is NOT caught by case 1. That half is closed by the runner's PRE-FLIGHT
    refusal (a configured server with no context_limit_tokens in cfg), which is the other brace: the
    two close DISJOINT halves and neither may be retired as redundant.
  - Only repo files are covered (site-packages are not).
"""
from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

REPO = Path(__file__).resolve().parents[3]
ROOT = REPO / "experiments" / "orchestration"


class TornTree(RuntimeError):
    """The runner and its coordinator child loaded different bytes for the same file."""


def _sha(p: Path) -> Optional[str]:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return None


def _rel(p: Path) -> Optional[str]:
    try:
        return str(p.resolve().relative_to(REPO))
    except ValueError:
        return None


def loaded_repo_files(modules: Optional[Iterable[Any]] = None) -> Dict[str, str]:
    """{repo-relative path: sha256 of the file on disk} for every loaded module under the repo."""
    out: Dict[str, str] = {}
    for m in list(modules if modules is not None else sys.modules.values()):
        f = getattr(m, "__file__", None)
        if not f or not str(f).endswith(".py"):
            continue
        r = _rel(Path(f))
        if r is None:
            continue
        h = _sha(Path(f))
        if h is not None:
            out[r] = h
    return out


def all_repo_py(root: Path = ROOT) -> Dict[str, Any]:
    """Every .py under `root` (no __pycache__), hashed. Returns {"files": {...}, "wall_s": t}."""
    t0 = time.perf_counter()
    files: Dict[str, str] = {}
    for p in sorted(root.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        r = _rel(p)
        h = _sha(p)
        if r is not None and h is not None:
            files[r] = h
    return {"files": files, "wall_s": round(time.perf_counter() - t0, 4)}


def _digest(m: Dict[str, str]) -> str:
    return hashlib.sha256("\n".join(f"{k} {v}" for k, v in sorted(m.items())).encode()).hexdigest()[:16]


def check_start(runner_loaded: Dict[str, str], child_loaded: Dict[str, str]) -> Dict[str, Any]:
    """Case 1. Raises TornTree on any overlap mismatch; otherwise returns the start record."""
    overlap = sorted(set(runner_loaded) & set(child_loaded))
    bad = [f for f in overlap if runner_loaded[f] != child_loaded[f]]
    rec = dict(runner_loaded_n=len(runner_loaded), child_loaded_at_start_n=len(child_loaded),
               overlap_n=len(overlap),
               runner_only_n=len(set(runner_loaded) - set(child_loaded)),
               child_only_at_start_n=len(set(child_loaded) - set(runner_loaded)),
               runner_digest=_digest(runner_loaded), child_start_digest=_digest(child_loaded),
               runner_child_mismatch=bad)
    if bad:
        raise TornTree(f"runner and coordinator child loaded different bytes for {len(bad)} "
                       f"file(s): {bad[:5]} (case 1 runner_child_mismatch; the cell must not run)")
    return rec


def check_end(start_all: Dict[str, str], child_loaded_at_start: Dict[str, str],
              child_loaded_at_end: Dict[str, str], end_all: Dict[str, str]) -> Dict[str, Any]:
    """Cases 2 and 3, from the child's START and END full-tree maps and its loaded sets."""
    moved_after_import: List[str] = []
    torn_lazy_import: List[str] = []
    for f in sorted(child_loaded_at_end):
        s, e = start_all.get(f), end_all.get(f)
        if s is None or e is None or s == e:
            continue
        (moved_after_import if f in child_loaded_at_start else torn_lazy_import).append(f)
    changed_anywhere = sorted(f for f in set(start_all) | set(end_all)
                              if start_all.get(f) != end_all.get(f))
    verdict = ("INVALID torn_lazy_import" if torn_lazy_import
               else "WARNING moved_after_import" if moved_after_import else "OK")
    return dict(verdict=verdict, torn_lazy_import=torn_lazy_import,
                moved_after_import=moved_after_import,
                child_only_late_n=len(set(child_loaded_at_end) - set(child_loaded_at_start)),
                tree_files_changed_during_cell=changed_anywhere[:50],
                tree_files_changed_during_cell_n=len(changed_anywhere))


NOTE = ("sha256 of files ON DISK (did the tree move under the cell, not what bytecode executed). "
        "Case 1 runner_child_mismatch -> TornTree before running; case 2 moved_after_import -> "
        "WARNING, cell kept (an imported module is cached, the change did not execute); case 3 "
        "torn_lazy_import -> INVALID. Bounds: a file changed and changed back within a cell is "
        "invisible; runner-only files are outside case 1 and are covered by the runner's pre-flight "
        "refusal instead (disjoint halves, keep both); repo files only.")
