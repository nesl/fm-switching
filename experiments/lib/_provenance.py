"""Provenance stamp utility for FM-switching experiments.

Usage:
    from _provenance import stamp
    result["_provenance"] = stamp(script="representation_frontier.py",
                                   model="qwen7b", device="a6000", n=500)
"""
import subprocess
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=_REPO_ROOT,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def stamp(*, script: str, model: str, device: str = None,
          n: int = None, seed: int = None, args=None) -> dict:
    """Return a provenance dict to embed as result['_provenance'].

    Parameters
    ----------
    script  : canonical script name (e.g. 'representation_frontier.py')
    model   : model slug (e.g. 'qwen7b', 'smollm2')
    device  : device slug (e.g. 'a6000', 'jetson') — None when device-independent
    n       : number of samples scored
    seed    : RNG seed if determinism matters
    args    : argparse.Namespace — stored as args dict for full reproducibility
    """
    prov = {
        "git_commit": _git_commit(),
        "script": script,
        "model": model,
        "timestamp": datetime.now().isoformat(),
    }
    if device is not None:
        prov["device"] = device
    if n is not None:
        prov["n"] = n
    if seed is not None:
        prov["seed"] = seed
    if args is not None:
        import argparse
        prov["args"] = vars(args) if isinstance(args, argparse.Namespace) else args
    return prov
