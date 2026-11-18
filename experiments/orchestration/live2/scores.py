#!/usr/bin/env python3
"""The committed score extractors, loaded FROM the committed study scripts. CPU only.

StudyLIVE2-fix2. The calibration (`live2/calib.py`) and the dashcam AP scorer
(`live2/scorer/score.py`) consume the SAME score object the committed studies produced, so this
module does not re-implement the extraction: it parses the committed script and executes the one
function it needs, so there is no second copy that can drift.

  * the dashcam SH score is `log(p_yes)` with `p_yes` from StudyD3 / StudyD14b's `yes_no`
    (`experiments/dashcam/d3_infer_vllm.py` lines 96-102). StudyCTRL1c states the definition and
    takes the same log: `experiments/dashcam/ctrl1c_calibrate.py` lines 276-277 and 298
    ("StudyD14b's committed `score` is log(p_yes) ... so log(p_yes) is taken here").
  * the robot recall letter is StudyR1's `score` (`experiments/sember/study_r1_vllm.py` lines
    101-110) with its module-level `LETTER` and `END`.

`p_yes` is None when the first token's top-20 carries neither Yes nor No; StudyD3 records that as
`neither` and StudyCTRL1c's fit never sees such a row, so the score here is None too. None is
UNKNOWN, never a number: the scorer refuses AP on a missing score rather than mixing a cloud
decision with a device score, which is the behaviour this module must preserve.

NOTHING HERE MEASURES ANYTHING.
"""
from __future__ import annotations

import ast
import math
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[3]
D3_SCRIPT = ROOT / "experiments/dashcam/d3_infer_vllm.py"
R1_SCRIPT = ROOT / "experiments/sember/study_r1_vllm.py"
O_Q4_SCRIPT = ROOT / "experiments/sember/study_o_q4.py"
CTRL1C_SCRIPT = ROOT / "experiments/dashcam/ctrl1c_calibrate.py"

SCORE_DEFINITION = "log(p_yes), identical to StudyD14b's committed `score` (StudyCTRL1c)"


def load_committed(path: Path, func: str, consts: Sequence[str] = ()) -> Callable[..., Any]:
    """Execute ONE function (and the module constants it closes over) out of a committed script.

    The script itself is never imported: StudyD3's module body starts a server path, opens
    `httpx` and rewrites `sys.path`, none of which may happen in the coordinator's process.
    """
    src = path.read_text()
    tree = ast.parse(src, filename=str(path))
    want = set(consts)
    body: List[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in want for t in node.targets):
            body.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name == func:
            body.append(node)
    names = [n.name for n in body if isinstance(n, ast.FunctionDef)]
    if names != [func]:
        raise RuntimeError(f"{path.name} no longer defines exactly one `{func}`: {names}")
    got = {t.id for n in body if isinstance(n, ast.Assign) for t in n.targets
           if isinstance(t, ast.Name)}
    if got != want:
        raise RuntimeError(f"{path.name}: expected constants {sorted(want)}, found {sorted(got)}")
    ns: Dict[str, Any] = {"math": math, "re": re, "__name__": f"committed_{path.stem}"}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), ns)   # noqa: S102
    return ns[func]


def committed_constant(path: Path, name: str) -> Any:
    """One module-level constant out of a committed script, evaluated not retyped."""
    tree = ast.parse(path.read_text(), filename=str(path))
    ns: Dict[str, Any] = {"__name__": f"committed_{path.stem}"}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
        # earlier constants are executed too, because a later one may be built from them; a
        # constant that needs an import stays unevaluated and is simply skipped
        try:
            exec(compile(ast.Module(body=[node], type_ignores=[]),            # noqa: S102
                         str(path), "exec"), ns)
        except Exception:                                                     # noqa: BLE001
            continue
        if name in targets:
            return ns[name]
    raise RuntimeError(f"{path.name} defines no evaluable module-level {name}")


yes_no = load_committed(D3_SCRIPT, "yes_no")
r1_score = load_committed(R1_SCRIPT, "score", consts=("LETTER", "END"))


def sh_score(logprobs: Optional[Sequence[Dict[str, Any]]]) -> Dict[str, Any]:
    """StudyD3's `yes_no` on a first-token top-20, then StudyCTRL1c's log.

    `logprobs` is the OpenAI `logprobs.content` list, which is what both the non-streaming
    StudyD3 body and a streamed body carry; the extractor reads element 0 either way.
    """
    p, mass_yes, mass_no = yes_no(list(logprobs) if logprobs else None)
    score = None if p is None or p <= 0.0 else math.log(p)
    return dict(cloud_score=score, p_yes=p, mass_yes=mass_yes, mass_no=mass_no,
                neither=(p is None), score_definition=SCORE_DEFINITION)


def recall_letter(text: str, thinking: bool = False) -> Dict[str, Any]:
    """StudyR1's `score`: the LAST A-E in the last 300 characters of the answer, else 'X'."""
    closed, pred = r1_score(text or "", thinking)
    return dict(cloud_letter=pred, think_closed=closed)


def first_token_logprobs(chunks: Sequence[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """The `logprobs.content` of the FIRST generated token out of streamed chunks.

    A streamed chat completion carries one `logprobs.content` entry per delta, so the first
    non-empty entry is the first generated token: the same element StudyD3 reads at index 0 of a
    non-streamed response.
    """
    for ch in chunks or ():
        content = ((ch.get("logprobs") or {}).get("content")) or []
        if content:
            return list(content)
    return None
