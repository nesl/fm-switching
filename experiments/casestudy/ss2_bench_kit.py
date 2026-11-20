#!/usr/bin/env python3
"""StudySS2 shared benchmark kit: prompts, image preprocessing, and scorers for the three CPS
single-shot candidates. Imported by the manifest builder, the device/cloud runner and (for CODA-LM)
the judge runner, so the device (Orin, Qwen3-VL-4B under vLLM) and the H100 cloud (32B) are scored
by identical code.

No model is run here. Same discipline as StudySS1: one prompt template per dataset, one shared
preprocessing path, deterministic local scorers where the benchmark allows it, judge spec recorded
for the pass that needs one. No em dashes.

Datasets and licences (checked before any download; see reports/study_ss2.md):
  1. RefSpatial-Bench (BAAI/RefSpatial-Bench) - Apache-2.0, 277 items (location 100, placement 100,
     unseen 77). Output = point(s); score = fraction of predicted points inside the GT binary mask.
     Prompt + parsing + scoring reproduced from the official RoboRefer eval code
     (github.com/Zhoues/RoboRefer, Evaluation/test_benchmark.py get_prompt + summarize_acc.py).
  2. RealWorldQA (xai-org/RealworldQA) - CC BY-ND 4.0, 765 items. Exact match after the benchmark's
     normalisation; MCQ (gold answer in {A,B,C,D}) vs free-form reported separately. Prompt +
     detection + normalisation reproduced from lmms-eval's realworldqa task (the harness that splits
     the two subsets): lmms_eval/tasks/realworldqa/utils.py realworldqa_process_results. ND licence:
     images are NOT committed.
  3. CODA-LM test (KaiChen1998/coda-lm) - annotations Apache-2.0, but the IMAGES come from the CODA
     dataset under CC BY-NC-SA 4.0 + Huawei "Dataset Terms" (non-commercial, redistribution
     PROHIBITED), accepted by downloading. Per the StudySS2 rule ("if any part needs an agreement,
     skip CODA-LM and report"), the CODA-LM RUN IS SKIPPED on this box: no CODA images are
     downloaded and no answers are produced. The judge prompts are recorded below (CODA_LM_JUDGE_*)
     so the user can lift the skip; the gpt-4o judge is a separate pass on another box if enabled.
"""
from __future__ import annotations

import base64
import io
import json
import re
from typing import List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

# ============================================================ image preprocessing (shared, == SS1)
JPEG_QUALITY = 90
MAX_SIDE = 2048   # bound memory on very large photos; RefSpatial/RealWorldQA are well below this


def preprocess_to_jpeg_bytes(path: str) -> bytes:
    """The ONE shared preprocessing path for both tiers (identical to StudySS1): open, convert to
    RGB, downscale only if the longest side exceeds MAX_SIDE (Lanczos), re-encode as JPEG quality
    90. The identical bytes are sent to the device 4B and the cloud 32B; each model then applies its
    own released image processor, so the only preprocessing we impose is this re-encode."""
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


def image_dims(path: str) -> Tuple[int, int]:
    """(width, height) of the image AS SENT to the model, i.e. after the shared preprocessing. For
    RefSpatial the mask is at the original resolution and the images are far below MAX_SIDE, so the
    sent dims equal the original dims and predicted pixel coordinates index the mask directly."""
    with Image.open(path) as im:
        w, h = im.size
    m = max(w, h)
    if m > MAX_SIDE:
        s = MAX_SIDE / float(m)
        return max(1, round(w * s)), max(1, round(h * s))
    return w, h


def jpeg_data_url(path: str) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(preprocess_to_jpeg_bytes(path)).decode()


# ============================================================ RefSpatial-Bench
# Prompt: the official RoboRefer get_prompt() Qwen branch (test_benchmark.py). Qwen3-VL is a Qwen
# VLM, so the benchmark's Qwen branch is the faithful "benchmark's own prompt" for both our tiers.
def refspatial_prompt(obj: str) -> str:
    return "Locate %s in this image and output the point coordinates in JSON format." % obj.strip()


# The official summarize_acc.py dispatches Qwen -> text2pts(is_absolute=True): absolute pixel
# coordinates, parsed from "(x, y)" tuples. Qwen3-VL, told to answer in JSON, emits a JSON list of
# {"point"/"point_2d"/"coordinate": [x, y]} (or bare [x, y] pairs). We parse BOTH the JSON forms and
# the tuple form into (x, y) pairs.
#
# COORDINATE CONVENTION (validated before the full sweep; CLAUDE.md Step 2b). Qwen3-VL emits
# coordinates NORMALISED to 0..1000 (x_norm = x_px / W * 1000, y_norm = y_px / H * 1000), NOT the
# absolute pixels the RoboRefer Qwen branch assumed (that was Qwen2.5-VL). Evidence on the 9-item
# smoke: these 640x480 images are within Qwen3-VL's pixel budget so no internal resize happens, yet
# predicted coordinates reach y=971 / x=800 which absolute pixels could never exceed; under
# "absolute" 4 of 9 points fall out of bounds and mean accuracy is 0.000 (a scoring artifact), while
# under "norm1000" all 9 points are in bounds and mean accuracy is non-zero. COORD_MODE is applied
# identically to device and cloud by the shared kit.
COORD_MODE = "norm1000"   # one of: "absolute" (pixels), "norm01" (0..1), "norm1000" (0..1000)

_TUPLE_RE = re.compile(r"\(\s*([-+]?\d+\.?\d*)\s*,\s*([-+]?\d+\.?\d*)\s*\)")
_PAIR_RE = re.compile(r"\[\s*([-+]?\d+\.?\d*)\s*,\s*([-+]?\d+\.?\d*)\s*\]")
_POINT_KEYS = ("point_2d", "point", "coordinate", "coord", "center", "xy", "position", "location")


def _scale_xy(x: float, y: float, width: int, height: int, mode: str) -> Tuple[float, float]:
    if mode == "norm01":
        return x * width, y * height
    if mode == "norm1000":
        return x / 1000.0 * width, y / 1000.0 * height
    return x, y   # absolute


def _iter_json_points(obj, out):
    """Walk a parsed JSON object collecting any 2-number coordinate under a known key, or any bare
    2-element numeric list."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in _POINT_KEYS and isinstance(v, list) and len(v) == 2 \
                    and all(isinstance(z, (int, float)) for z in v):
                out.append((float(v[0]), float(v[1])))
            else:
                _iter_json_points(v, out)
    elif isinstance(obj, list):
        if len(obj) == 2 and all(isinstance(z, (int, float)) for z in obj):
            out.append((float(obj[0]), float(obj[1])))
        else:
            for v in obj:
                _iter_json_points(v, out)


def refspatial_parse_points(text: str, width: int, height: int,
                            mode: str = None) -> np.ndarray:
    """Parse model text into an (N, 2) int array of (x, y) pixel coordinates. Tries JSON point forms
    first (list of {"point": [x, y]} etc., or bare [x, y] pairs), then the official "(x, y)" tuple
    regex. Coordinates are mapped to pixels per COORD_MODE. Returns an empty (0, 2) array if nothing
    parses (scored as 0, exactly as the benchmark does)."""
    mode = mode or COORD_MODE
    pts: List[Tuple[float, float]] = []
    # 1) JSON block(s)
    for m in re.finditer(r"\{.*\}|\[.*\]", text, re.DOTALL):
        try:
            _iter_json_points(json.loads(m.group(0)), pts)
        except Exception:
            pass
        if pts:
            break
    # 2) bare [x, y] pairs if JSON parse found nothing
    if not pts:
        for a, b in _PAIR_RE.findall(text):
            pts.append((float(a), float(b)))
    # 3) official "(x, y)" tuple form
    if not pts:
        for a, b in _TUPLE_RE.findall(text):
            pts.append((float(a), float(b)))
    if not pts:
        return np.empty((0, 2), dtype=int)
    scaled = [_scale_xy(x, y, width, height, mode) for x, y in pts]
    return np.array([(int(round(x)), int(round(y))) for x, y in scaled], dtype=int)


def refspatial_point_accuracy(points: np.ndarray, mask: np.ndarray) -> float:
    """Reproduces summarize_acc.py compute_accuracy for one sample: per-sample accuracy = fraction
    of predicted points that fall inside the binary mask. mask is a binarised (H, W) uint8 array
    (mask > 0). In-image points are looked up at mask[y, x]; out-of-bounds points count as explicit
    zeros (they drag the score down, not dropped). No points -> 0.0."""
    if points is None or len(points) == 0:
        return 0.0
    H, W = mask.shape[:2]
    x = points[:, 0]
    y = points[:, 1]
    in_range = (x >= 0) & (x < W) & (y >= 0) & (y < H)
    hits = mask[y[in_range], x[in_range]]
    vals = np.concatenate([hits, np.zeros(points.shape[0] - int(in_range.sum()))])
    return float(vals.mean())


def load_binary_mask(path: str) -> np.ndarray:
    """summarize_acc.py mask load: open PNG, /255, take channel 0 if 3-D, binarise (>0)."""
    m = np.array(Image.open(path)) / 255.0
    if m.ndim == 3:
        m = m[:, :, 0]
    return (m > 0).astype(np.uint8)


# ============================================================ RealWorldQA
# lmms-eval realworldqa task: the prompt is the dataset's own question text, unchanged (the question
# already embeds its instruction, e.g. "Please answer directly with a single word or number." or the
# lettered options). We add nothing (default pre/post prompt empty).
def realworldqa_prompt(question: str) -> str:
    return question.strip()


def realworldqa_is_mcq(gold: str) -> bool:
    """lmms-eval detection: the item is MCQ iff the gold answer is a single letter A/B/C/D."""
    return gold.strip().upper() in ("A", "B", "C", "D")


_BOXED_RE = re.compile(r"\\boxed\{([^}]*)\}")
_ANSWER_TAG_RE = re.compile(r"<answer>(.*?)</answer>", re.DOTALL | re.IGNORECASE)
_DECLARED_RE = re.compile(r"(?i)\b(?:the\s+)?(?:correct\s+)?answer\s*(?:is|:)\s*\(?\*{0,2}([A-D])\b")


def extract_mcq_answer(response: str, choices=("A", "B", "C", "D")) -> str:
    """Conservative reimplementation of lmms-eval _task_utils.mcq_extract.extract_mcq_answer: return
    an uppercase option letter, or "" (abstain, scored 0). Honours a final \\boxed{}/<answer>
    container, an explicit "Answer: X" declaration, then a bare/parenthesised standalone letter;
    abstains when the text names more than one distinct option letter (ambiguous)."""
    allowed = {c.upper() for c in choices if len(c) == 1 and c.isalpha()}
    if not response or not response.strip():
        return ""
    # a container wins if present and unambiguous
    scope = None
    tags = _ANSWER_TAG_RE.findall(response)
    if tags:
        scope = tags[-1].strip()
    else:
        bx = _BOXED_RE.findall(response)
        if bx:
            scope = bx[-1].strip()
    for region in ([scope] if scope is not None else []) + [response]:
        if region is None:
            continue
        md = _DECLARED_RE.search(region)
        if md and md.group(1).upper() in allowed:
            return md.group(1).upper()
        # standalone single letters as whole tokens
        toks = re.findall(r"[A-Za-z]+", region)
        letters = [t.upper() for t in toks if len(t) == 1 and t.upper() in allowed]
        uniq = sorted(set(letters))
        if len(uniq) == 1:
            return uniq[0]
        if len(uniq) > 1:
            return ""   # ambiguous
    return ""


def realworldqa_score(prediction: str, gold: str) -> Tuple[float, str]:
    """lmms-eval realworldqa_process_results. Returns (score in {0.0, 1.0}, subset in
    {"mcq", "free_form"}). MCQ: extracted letter == gold letter. Free-form: lowercase, strip, drop a
    trailing period, exact string equality against the lowercased gold."""
    g = gold.strip()
    if realworldqa_is_mcq(g):
        pred = extract_mcq_answer(prediction, ("A", "B", "C", "D"))
        return (1.0 if pred == g.upper() else 0.0), "mcq"
    pred_clean = prediction.lower().strip().rstrip(".")
    return (1.0 if pred_clean == g.lower() else 0.0), "free_form"


# ============================================================ CODA-LM judge spec (RUN SKIPPED here)
# Recorded verbatim from the CODA-LM eval code (evaluation/stage{1,2,3}_eval_batch.py) so the user
# can lift the SKIP. Judge model per evaluation/README.md: gpt-4o-2024-05-13, temperature 0, rating
# 1..10 parsed as "Rating: [[x]]". The CODA-LM run is skipped on this box (CODA image terms gate);
# no answers are produced, so these are documentation only.
CODA_LM_GENERATION_PROMPTS = {
    "general_perception": (
        "There is an image of traffic captured from the perspective of the ego car. Focus on "
        "objects influencing the ego car's driving behavior: vehicles (cars, trucks, buses, etc.), "
        "vulnerable road users (pedestrians, cyclists, motorcyclists), traffic signs (no parking, "
        "warning, directional, etc.), traffic lights (red, green, yellow), traffic cones, barriers, "
        "miscellaneous(debris, dustbin, animals, etc.). You must not discuss any objects beyond the "
        "seven categories above. Please describe each object's appearance, position, direction, and "
        "explain why it affects the ego car's behavior."),
    "driving_suggestion": (
        "There is an image of traffic captured from the perspective of the ego car. Focus on "
        "objects influencing the ego car's driving behavior: vehicles (cars, trucks, buses, etc.), "
        "vulnerable road users (pedestrians, cyclists, motorcyclists), traffic signs (no parking, "
        "warning, directional, etc.), traffic lights (red, green, yellow), traffic cones, barriers, "
        "miscellaneous(debris, dustbin, animals, etc.). You must not discuss any objects beyond the "
        "seven categories above. Please provide driving suggestions for the ego car based on the "
        "current scene."),
    "region_perception": (
        "Please describe the object inside the red rectangle in the image and explain why it affect "
        "ego car driving."),
}
CODA_LM_JUDGE_USER_TEMPLATE = ("[The Start of Reference Text]\n{ref}\n[The End of Reference Text]\n\n"
                               "[The Start of Prediction Text]\n{pred}\n[The End of Prediction Text]")
CODA_LM_JUDGE_MODEL = "gpt-4o-2024-05-13"


def parse_rating_1to10(text: str) -> Optional[int]:
    """CODA-LM / judge rating parse: 'Rating: [[x]]' with 1..10 fallbacks, int in [1, 10] or None."""
    if not text:
        return None
    for marker in ("Rating: [[", "rating is: [[", "[["):
        if marker in text:
            try:
                v = int(text.split(marker, 1)[1].split("]]", 1)[0].strip())
                if 1 <= v <= 10:
                    return v
            except Exception:
                pass
    return None
