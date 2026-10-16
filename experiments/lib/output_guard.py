"""Refuse to silently overwrite a committed report.

StudyP's FA2 re-run overwrote `reports/study_p_retry_vs_scale.md` in place: REPORT_PATH was
hard-coded while --fa2 redirected only the trials JSONL, so a backend re-run replaced the
committed SDPA accuracy, termination and latency numbers under the original filename. Nothing
in the script could notice. This module makes that class of accident structural rather than
something each script has to remember.

Writing a NEW report is always allowed. Replacing one that git already tracks is not, unless
the caller says so explicitly.
"""

import os
import subprocess
from pathlib import Path

ENV_OVERRIDE = "FM_ALLOW_REPORT_OVERWRITE"


def _tracked(path):
    """True if git tracks this path. Treated as untracked outside a work tree."""
    try:
        r = subprocess.run(["git", "ls-files", "--error-unmatch", str(path)],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


def _suggest(path):
    p = Path(path)
    return str(p.with_name(p.stem + "_rerun" + p.suffix))


def guard_report(path, *, allow_overwrite=False, note=""):
    """Abort unless `path` is safe to write. Returns the path for chaining.

    allow_overwrite=True is the deliberate in-place regeneration of a committed report —
    pass it only when the run reproduces the same configuration the report was built from.
    """
    path = str(path)
    if not allow_overwrite and _tracked(path):
        if os.environ.get(ENV_OVERRIDE) == "1":
            print(f"  [output_guard] {ENV_OVERRIDE}=1 — overwriting tracked {path}", flush=True)
            return path
        raise SystemExit(
            f"FATAL [output_guard]: refusing to overwrite the committed report\n"
            f"    {path}\n"
            f"{('    ' + note + chr(10)) if note else ''}"
            f"  This file is tracked in git. A run whose configuration differs from the one that\n"
            f"  produced it (different backend, host, seed or arm set) must write somewhere else,\n"
            f"  or the committed numbers are replaced with no record that they changed.\n"
            f"  Either point the script at a new path, e.g.\n"
            f"    {_suggest(path)}\n"
            f"  or, if this run genuinely reproduces the committed configuration, re-run with\n"
            f"    {ENV_OVERRIDE}=1")
    return path


def report_path_for(base, *, suffix=None, allow_overwrite=False, note=""):
    """Build a run-tagged report path and guard it in one step.

    `suffix` is the run tag that distinguishes this configuration — a backend, host or arm
    label. With no suffix this is just guard_report(base).
    """
    if suffix:
        p = Path(base)
        base = str(p.with_name(f"{p.stem}_{suffix}{p.suffix}"))
    return guard_report(base, allow_overwrite=allow_overwrite, note=note)
