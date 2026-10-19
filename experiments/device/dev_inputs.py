#!/usr/bin/env python3
"""
DEV-RECENT: the device's own input construction for S-EMBER QA on the llama.cpp
image path. Importable by both the Orin (latency) and the A6000 (accuracy) so the
two measure the IDENTICAL inputs.

Definition
----------
- Frames: uniformly spaced over [question_time - 120 s, question_time], no frame
  after question_time, in time order. Each frame is preceded in the prompt text by
  its timestamp as "[t=XXs]". Frames are passed to llama.cpp as SEPARATE IMAGES
  (not a video); there is NO temporal merging (this is the device's own construction,
  deliberately not Study O's HF video path).
- Resolution: every frame is resized to exactly 560x560 with PIL LANCZOS
  (Image.resize((560,560), LANCZOS)); aspect ratio is NOT preserved (fixed square),
  so the per-frame visual-token count is constant (content- and source-independent).
- Budget: N = the largest frame count such that total input tokens (images + marker
  text + question/options/instruction) stay <= TOKEN_BUDGET (12,500). N is fixed
  across questions for comparable latency; see choose_n() / verify.
- Prompt text & answer format: copied verbatim from experiments/sember/study_o_q4.py
  (same question, options, answer instruction), with per-frame "[t=XXs]" markers added.

DEV-RICH (added 2026-10-18) is the second construction: IDENTICAL in every respect
-- same N, same 560x560 frames, same "[t=XXs]" markers, same prompt, same 12,500
token budget -- except that the frames are uniformly spaced over [0, question_time]
instead of [question_time - 120 s, question_time]. It is a reallocation of the same
token budget across the whole session rather than the last 120 s, not more tokens.
DEV-RECENT's own functions are untouched so the Orin's latency rows stay reproducible.

The only measured constant is per-frame image tokens at 560x560 (PER_FRAME_IMAGE_TOKENS),
determined empirically against the llama-server tokenizer and recorded here.
"""
import base64, io, json, math, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MCQ_PATH = ROOT / "results/sember/study_h/data/sember_mcq.jsonl"

WINDOW_S = 120.0
RESOLUTION = (560, 560)
TOKEN_BUDGET = 12500
# Calibrated against this build's llama-server (Qwen3-VL-4B mmproj-F16): a 560x560
# image plus its "[t=XXs]" marker costs ~332 tokens; tokens are content-independent
# at fixed resolution (measured 5f=1823, 15f=5142, 30f=10123 -> 332/frame, ~163
# text/overhead intercept). N=37 is the largest frame count with 37*332+text <= 12500
# for typical questions. See reports/device_latency_sember.md.
PER_FRAME_IMAGE_TOKENS = 332   # calibrated (560x560, incl. per-frame marker)
DEV_RECENT_N = 37              # calibrated budget frame count

ANSWER_INSTR = ("\n\nReply with only the letter of the correct answer "
                "(A, B, C, D, or E).")


def load_mcq(path=MCQ_PATH):
    """question_id -> record (question, options, correct_letter, question_time,
    answer_start_time, answer_end_time, video_id, question_category)."""
    out = {}
    for line in open(path):
        r = json.loads(line)
        out[r["question_id"]] = r
    return out


def frame_times(question_time, n):
    """N timestamps uniformly spaced over [max(0, qt-120), qt], rounded to whole
    seconds (the cached frames are at 1 fps), in time order, deduplicated."""
    qt = float(question_time)
    lo = max(0.0, qt - WINDOW_S)
    if n <= 1:
        return [int(round(qt))]
    raw = [lo + (qt - lo) * i / (n - 1) for i in range(n)]
    ts = sorted(set(int(round(t)) for t in raw))
    return ts


def frame_times_rich(question_time, n):
    """DEV-RICH: N timestamps uniformly spaced over [0, question_time], rounded to
    whole seconds (the cached frames are at 1 fps), in time order, deduplicated.

    Same contract as frame_times() but with lo pinned to the session start instead
    of question_time - WINDOW_S. No frame after question_time."""
    qt = float(question_time)
    lo = 0.0
    if n <= 1:
        return [int(round(qt))]
    raw = [lo + (qt - lo) * i / (n - 1) for i in range(n)]
    ts = sorted(set(int(round(t)) for t in raw))
    return ts


def frame_times_for(construction, question_time, n):
    """Dispatch to the construction's sampler. construction in {RECENT, RICH}."""
    if construction == "RECENT":
        return frame_times(question_time, n)
    if construction == "RICH":
        return frame_times_rich(question_time, n)
    raise ValueError(f"unknown construction {construction!r}")


def nearest_available(ts, available_sorted):
    """Map each desired timestamp to the nearest actually-decoded frame timestamp."""
    import bisect
    out = []
    for t in ts:
        i = bisect.bisect_left(available_sorted, t)
        cands = []
        if i < len(available_sorted):
            cands.append(available_sorted[i])
        if i > 0:
            cands.append(available_sorted[i-1])
        out.append(min(cands, key=lambda a: abs(a - t)) if cands else t)
    # preserve order, dedupe
    seen, res = set(), []
    for t in out:
        if t not in seen:
            seen.add(t); res.append(t)
    return res


def resize_560_b64(img_path_or_pil):
    """Load, resize to 560x560 (LANCZOS, no aspect preservation), return PNG base64."""
    from PIL import Image
    im = img_path_or_pil if hasattr(img_path_or_pil, "resize") else Image.open(img_path_or_pil)
    im = im.convert("RGB").resize(RESOLUTION, Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def question_text(rec):
    """The Study O prompt, verbatim, minus the video sentence's 'video' noun which we
    keep as-is for faithfulness ('Watch the video carefully')."""
    return ("Watch the video carefully, then answer the following "
            f"multiple-choice question.\n\nQuestion: {rec['question']}\n\n"
            + "\n".join(rec["options"]) + ANSWER_INSTR)


def build_chat_content(rec, frame_items):
    """frame_items: list of (timestamp_int, base64_png). Returns an OpenAI-style
    content array: for each frame a text '[t=XXs]' marker then the image, in time
    order, followed by the question/options/instruction text block."""
    content = []
    for t, b64 in frame_items:
        content.append({"type": "text", "text": f"[t={t}s]"})
        content.append({"type": "image_url",
                         "image_url": {"url": f"data:image/png;base64,{b64}"}})
    content.append({"type": "text", "text": question_text(rec)})
    return content


def estimate_text_tokens(rec, n, approx_tok_per_char=0.27):
    """Rough upper estimate of non-image tokens: question+options+instruction + N markers."""
    base = len(question_text(rec))
    markers = n * len("[t=123s]")
    return int((base + markers) * approx_tok_per_char) + 16


def choose_n(rec, per_frame=PER_FRAME_IMAGE_TOKENS, budget=TOKEN_BUDGET):
    """Largest N with N*per_frame (marker included in per_frame) + base question text
    <= budget, capped at 121 (1 fps over 120 s). Uses only base question/options text
    for the intercept (markers already in per_frame)."""
    base = int(len(question_text(rec)) * 0.27) + 16
    n = max(1, int((budget - base) // per_frame))
    return min(n, 121)
