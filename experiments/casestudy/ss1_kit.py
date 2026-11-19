#!/usr/bin/env python3
"""StudySS1 shared benchmark kit: prompts, image preprocessing, and scorers for VizWiz-VQA and
EgoThink. Imported by the manifest builder, the device/cloud runner and the judge runner, so the
device (Orin, Qwen3-VL-4B under vLLM) and the H100 cloud (32B) are scored by identical code.

No model is run here. Licences: VizWiz-VQA is CC BY 4.0; EgoThink is Apache-2.0 (images bundled in
the HuggingFace dataset, sourced from Ego4D which the authors acknowledge). No em dashes.

Protocols reproduced from the datasets' own code:
  * VizWiz / VQA accuracy: the official VQA v2 answer normalisation (contractions, articles,
    punctuation, digit words) and acc = mean over the 10 leave-one-out subsets of min(matches/3, 1).
    'unanswerable' is just another answer string, scored exactly as the dataset scores it.
  * EgoThink generation prompt: "Please let your answer be as short as possible. Question:
    {question} Short answer:"; max_new_tokens 30, except the 'assistance' and 'navigation'
    dimensions which are planning (300). (EgoThink gpt_eval.py.)
  * EgoThink judge (scorer a): the repo's `single-math-v2` judge prompt, a TEXT judge that is NOT
    shown the image and rates 0 / 0.5 / 1 as "Rating: [[x]]" (EgoThink judge_prompts.jsonl), run by
    an open non-Qwen3-VL model (Mistral-7B-Instruct-v0.2).
  * EgoThink scorer (b): normalised containment / exact match against the reference.
"""
from __future__ import annotations

import base64
import io
import re
from typing import Dict, List, Optional, Sequence

from PIL import Image

# ============================================================ image preprocessing (shared)
JPEG_QUALITY = 90
MAX_SIDE = 2048   # only to bound memory on very large phone photos; VizWiz/EgoThink are well below


def preprocess_to_jpeg_bytes(path: str) -> bytes:
    """The ONE shared preprocessing path for both tiers: open, convert to RGB, downscale only if the
    longest side exceeds MAX_SIDE (Lanczos), re-encode as JPEG quality 90. The identical bytes are
    sent to the device 4B and the cloud 32B; each model then applies its own released image
    processor. The only preprocessing we impose is this re-encode, so it is identical for both."""
    im = Image.open(path)
    im = im.convert("RGB")
    w, h = im.size
    m = max(w, h)
    if m > MAX_SIDE:
        s = MAX_SIDE / float(m)
        im = im.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


def jpeg_data_url(path: str) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(preprocess_to_jpeg_bytes(path)).decode()


# ============================================================ prompts (each dataset's protocol)
def vizwiz_prompt(question: str) -> str:
    """Standard VizWiz short-answer prompt with the explicit unanswerable option (the convention
    used by LLaVA-style VizWiz evaluations; matches the dataset's answerable/unanswerable scoring)."""
    return (question.strip() + "\nWhen the provided information is insufficient, respond with "
            "'Unanswerable'.\nAnswer the question using a single word or phrase.")


EGOTHINK_PLANNING_DIMS = {"assistance", "navigation"}


def egothink_prompt(question: str) -> str:
    """EgoThink's own generation prompt (gpt_eval.py)."""
    return "Please let your answer be as short as possible. Question: {q} Short answer:".format(
        q=question.strip())


def egothink_max_new_tokens(dimension: str) -> int:
    return 300 if dimension in EGOTHINK_PLANNING_DIMS else 30


def egothink_clean_output(text: str) -> str:
    """EgoThink strips a leading 'Short Answer: ' echo if present."""
    if "Short Answer: " in text:
        text = text.split("Short Answer: ", 1)[1]
    return text.strip()


# ============================================================ VQA accuracy (official VQA v2)
_CONTRACTIONS = {
    "aint": "ain't", "arent": "aren't", "cant": "can't", "couldve": "could've",
    "couldnt": "couldn't", "didnt": "didn't", "doesnt": "doesn't", "dont": "don't",
    "hadnt": "hadn't", "hasnt": "hasn't", "havent": "haven't", "hed": "he'd", "hes": "he's",
    "howd": "how'd", "howll": "how'll", "hows": "how's", "Id": "I'd", "Im": "I'm", "Ive": "I've",
    "isnt": "isn't", "itd": "it'd", "itll": "it'll", "lets": "let's", "maam": "ma'am",
    "mightve": "might've", "mustnt": "mustn't", "mustve": "must've", "shes": "she's",
    "shouldve": "should've", "shouldnt": "shouldn't", "somebodyll": "somebody'll",
    "someoned": "someone'd", "someonell": "someone'll", "theres": "there's", "theyd": "they'd",
    "theyll": "they'll", "theyre": "they're", "theyve": "they've", "wasnt": "wasn't",
    "wed": "we'd", "weve": "we've", "werent": "weren't", "whatll": "what'll", "whatre": "what're",
    "whats": "what's", "whatve": "what've", "whos": "who's", "wont": "won't", "wouldve": "would've",
    "wouldnt": "wouldn't", "youd": "you'd", "youll": "you'll", "youre": "you're", "youve": "you've",
}
_MANUAL_MAP = {"none": "0", "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
               "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"}
_ARTICLES = {"a", "an", "the"}
_PERIOD_STRIP = re.compile(r"(?!<=\d)(\.)(?!\d)")
_COMMA_STRIP = re.compile(r"(\d)(\,)(\d)")
_PUNCT = [";", r"/", "[", "]", '"', "{", "}", "(", ")", "=", "+", "\\", "_", "-", ">", "<", "@",
          "`", ",", "?", "!"]


def _process_punctuation(s: str) -> str:
    out = s
    for p in _PUNCT:
        if (p + " " in s or " " + p in s) or (_COMMA_STRIP.search(s) is not None):
            out = out.replace(p, "")
        else:
            out = out.replace(p, " ")
    out = _PERIOD_STRIP.sub("", out, re.UNICODE)
    return out


def _process_digit_article(s: str) -> str:
    out = []
    for w in s.lower().split():
        w = _MANUAL_MAP.get(w, w)
        if w not in _ARTICLES:
            out.append(w)
    for i, w in enumerate(out):
        if w in _CONTRACTIONS:
            out[i] = _CONTRACTIONS[w]
    return " ".join(out)


def vqa_normalise(ans: str) -> str:
    """The official VQA v2 answer processing."""
    a = ans.replace("\n", " ").replace("\t", " ").strip()
    a = _process_punctuation(a)
    a = _process_digit_article(a)
    return a


def vqa_accuracy(prediction: str, gt_answers: Sequence[str]) -> float:
    """Official VQA accuracy for one question: the prediction is scored against each leave-one-out
    subset of the 10 human answers, acc = min(matches/3, 1), averaged over the 10 subsets. Requires
    exactly 10 ground-truth answers (VizWiz has 10)."""
    pred = vqa_normalise(prediction)
    gts = [vqa_normalise(g) for g in gt_answers]
    accs = []
    n = len(gts)
    for i in range(n):
        others = gts[:i] + gts[i + 1:]
        matches = sum(1 for o in others if o == pred)
        accs.append(min(matches / 3.0, 1.0))
    return float(sum(accs) / len(accs)) if accs else 0.0


# ============================================================ EgoThink scorers
_WORD = re.compile(r"[a-z0-9]+")


def _norm_text(s: str) -> str:
    return " ".join(_WORD.findall(s.lower()))


def egothink_containment(prediction: str, reference: str) -> float:
    """Scorer (b): 1.0 if the normalised reference is an exact match of, or a token-subsequence
    contained in, the normalised prediction (or vice versa for very short references); else 0.0."""
    p, r = _norm_text(prediction), _norm_text(reference)
    if not r:
        return 0.0
    if p == r:
        return 1.0
    return 1.0 if (r in p or p in r) else 0.0


EGOTHINK_JUDGE_SYSTEM = "You are a helpful assistant."
# EgoThink judge_prompts.jsonl, name "single-math-v2" (verbatim).
EGOTHINK_JUDGE_TEMPLATE = (
    "[Instruction]\nPlease act as an impartial judge and evaluate the quality of the response "
    "provided by an AI assistant to the user question displayed below. Your evaluation should "
    "consider correctness and helpfulness. You will be given a reference answer and the "
    "assistant's answer. Begin your evaluation by comparing the assistant's answer with the "
    "reference answer. Identify and correct any mistakes. The assistant has access to an image "
    "alongwith questions but you will not be given images. Therefore, please consider only how the "
    "answer is close to the reference answer. If the assistant's answer is not exactly same as or "
    "similar to the answer, then he must be wrong.  Be as objective as possible. Discourage "
    "uninformative answers. Also, equally treat short and long answers and focus on the correctness "
    "of answers.  After providing your explanation, you must rate the response with either 0, 0.5 "
    "or 1 by strictly following this format: \"[[rating]]\", for example: \"Rating: [[0.5]]\".\n\n"
    "[Question]\n{question}\n\n[The Start of Reference Answer]\n{ref_answer_1}\n[The End of "
    "Reference Answer]\n\n[The Start of Assistant's Answer]\n{answer}\n[The End of Assistant's "
    "Answer]")

_RATING = re.compile(
    # D139. The judge emits its rating in three observed shapes, and the original pattern
    # accepted only one of them: `[[x]]`. Measured over 700 Mistral-7B judgements, 667 failed
    # to parse, of which 399 were CORRECTLY double-bracketed and rejected only because the
    # value was written `1.0` or `0.0`, which `[01](?:\.5)?` does not match; 176 were a bare
    # `Rating: x` and 76 were single-bracketed `[x]`. Only 33 of 700 parsed. This accepts all
    # three shapes and the `.0` spellings, and still admits only the three legal values
    # 0, 0.5 and 1, which `parse_judge_rating` enforces after the match.
    r"(?:\[\[\s*([0-9]*\.?[0-9]+)\s*\]\]"
    r"|\[\s*([0-9]*\.?[0-9]+)\s*\]"
    r"|[Rr]ating\s*[:=]\s*([0-9]*\.?[0-9]+))")


def egothink_judge_prompt(question: str, reference: str, answer: str) -> str:
    return EGOTHINK_JUDGE_TEMPLATE.format(question=question, ref_answer_1=reference, answer=answer)


def parse_judge_rating(text: str) -> Optional[float]:
    """Parse the last rating as 0, 0.5 or 1; None if the judge did not emit one.

    Accepts `[[x]]`, `[x]` and a bare `Rating: x`, with or without a `.0`. Values outside
    {0, 0.5, 1} are rejected, so a looser match cannot admit an illegal rating. A rating stated
    only in prose ("I would rate it as 0") is deliberately NOT matched: extracting those would risk
    capturing unrelated numbers, and they are 16 of 700.
    """
    ms = _RATING.findall(text or "")
    if not ms:
        return None
    vals = [g for m in ms for g in (m if isinstance(m, tuple) else (m,)) if g]
    if not vals:
        return None
    try:
        v = float(vals[-1])
    except ValueError:
        return None
    return v if v in (0.0, 0.5, 1.0) else None