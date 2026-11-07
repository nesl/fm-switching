"""StudyB1-flash answer parsing. Each dataset uses its own upstream parser.

  rtv_extract_pred_letter          RTV-Bench scripts/utils/prompt_utils.py:16-36
  ovo_upstream                     OVO-Bench utils/OVOBenchScore.py:17-20 (letter: `gt in response`),
                                   :32-37 (REC: digits joined == str(count)),
                                   :39-42 + :57-66 (SSR/CRR: "Yes"/"No" in response, plus the
                                   literal "Y"/"N" short-circuit)
  herbench_extract_answer_choice   HERBench evaluation/model_wrappers/base_vlm.py:273-315
  streamingbench_first_char        StreamingBench src/data/count.py:65 `response[0]`

A Thinking response is split on the thinking block first; the upstream parser is then applied
to the answer segment only. Upstream never saw a reasoning model, so applying `gt in response`
to a chain of thought would score the reasoning, not the answer. This split is a documented
deviation, and `thinking_split_found` records whether a block was actually present.
"""
from __future__ import annotations

import re

UNPARSED = "__UNPARSED__"

THINK_CLOSE = re.compile(r"</think>|</thinking>|</thought>", re.I)


def split_thinking(text: str) -> tuple[str, bool]:
    """Return (answer_segment, found_block)."""
    if not text:
        return "", False
    m = None
    for m2 in THINK_CLOSE.finditer(text):
        m = m2
    if m:
        return text[m.end():].strip(), True
    return text.strip(), False


def rtv_extract_pred_letter(text: str, valid: set[str]) -> str:
    if not text:
        return UNPARSED
    up = text.upper()
    m = re.search(r"\b([A-Z])\b", up)
    if m and m.group(1) in valid:
        return m.group(1)
    m = re.search(r"(OPTION|ANSWER)\s*[:\-]?\s*([A-Z])", up)
    if m and m.group(2) in valid:
        return m.group(2)
    c0 = text.strip()[:1].upper()
    if c0 in valid:
        return c0
    return UNPARSED


def herbench_extract_answer_choice(text: str) -> str:
    if not text:
        return UNPARSED
    r = text.strip()
    if "ERROR" in r.upper():
        return UNPARSED
    for pat in (r"^([A-E])[\s\.\,\)]", r"^\(([A-E])\)", r"^([A-E])$",
                r"[Aa]nswer:\s*([A-E])\b", r"[Cc]hoice:\s*([A-E])\b", r"\b([A-E])\b[\.\,]"):
        m = re.search(pat, r)
        if m:
            return m.group(1).upper()
    up = r.upper()
    for m in re.finditer(r"([A-E])", up):
        a, b = m.start(1), m.end(1)
        before = up[a - 1] if a > 0 else " "
        after = up[b] if b < len(up) else " "
        if not before.isalpha() and not after.isalpha():
            return m.group(1)
    return UNPARSED


def streamingbench_first_char(text: str, valid: set[str]) -> str:
    if not text:
        return UNPARSED
    c = text.strip()[:1].upper()
    return c if c in valid else UNPARSED


def strict_letter(text: str, valid: set[str]) -> str:
    """Strict fallback: exactly one option letter may appear as a standalone token."""
    if not text:
        return UNPARSED
    found = {m.group(1) for m in re.finditer(r"\b([A-Z])\b", text.upper()) if m.group(1) in valid}
    return found.pop() if len(found) == 1 else UNPARSED


def score(row: dict, raw: str) -> dict:
    """Return parse + correctness under the row's own upstream parser."""
    ans, found_block = split_thinking(raw or "")
    kind = row["answer_kind"]
    gold = row["gold"]
    parser = row["parser"]
    out = {"answer_segment_chars": len(ans), "thinking_split_found": found_block}

    if kind == "letter":
        valid = set(row["options"].keys())
        if parser == "rtv_extract_pred_letter":
            pred = rtv_extract_pred_letter(ans, valid)
        elif parser == "herbench_extract_answer_choice":
            pred = herbench_extract_answer_choice(ans)
            if pred != UNPARSED and pred not in valid:
                pred = UNPARSED
        elif parser == "streamingbench_first_char":
            pred = streamingbench_first_char(ans, valid)
        elif parser == "ovo_upstream":
            # upstream: int(ground_truth in response) -- substring, not a parse
            pred = gold if gold in ans else strict_letter(ans, valid)
        else:
            pred = strict_letter(ans, valid)
        out["pred"] = pred
        out["correct"] = bool(pred == gold)
        out["unparsed"] = bool(pred == UNPARSED)
        out["pred_strict"] = strict_letter(ans, valid)
        out["correct_strict"] = bool(out["pred_strict"] == gold)

    elif kind == "count":
        digits = "".join(re.findall(r"\d+", ans))
        out["pred"] = digits if digits else UNPARSED
        out["correct"] = bool(digits == str(gold))
        out["unparsed"] = not digits

    elif kind == "yesno":
        if ans.strip() == "N":
            pred = "No"
        elif ans.strip() == "Y":
            pred = "Yes"
        else:
            has_y, has_n = ("Yes" in ans), ("No" in ans)
            pred = "Yes" if has_y and not has_n else "No" if has_n and not has_y else UNPARSED
        out["pred"] = pred
        out["correct"] = bool(gold in ans) or bool(pred == gold)
        out["unparsed"] = bool(pred == UNPARSED)
    else:
        raise ValueError(kind)

    out["empty"] = not (raw or "").strip()
    return out
