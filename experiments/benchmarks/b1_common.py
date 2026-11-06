#!/usr/bin/env python3
"""StudyB1-h100 shared code: items + fixed order, prompt templates, causal frame selection / rendering, parsers.

QUERY TIME (cited, see reports/study_b1_h100.md §Query time):
  OVO-Bench   single-query tasks: entry["realtime"]; forward tasks (REC / SSR / CRR): each test_info[j]["realtime"].
              Source: OVO-Bench code utils/chunk_videos.py (clip = [0, ceil(realtime)] per entry / per test_info j) and
              utils/OVOBench.py (one inference per entry / per test_info j on that clip).
  RTV-Bench   item["end_time"]. Source: RTV-Bench code scripts/infer/infer_model_rtv.py + scripts/utils/video_utils.py
              crop_video_ffmpeg (input video = [0, end_time]; clips [start_time, end_time] with start_time = 0 for all
              4,608 items) and README asset 1_examples.png ("in the current scene" answers labelled by timestamp).
  Here the query time t is used UNROUNDED (upstream ceil() can show up to 1 s past t; not like-for-like).
FRAMES: PyAV decode timestamps; each target takes the LATEST decoded frame with pts <= target (seek to the keyframe at
  or before the target, decode forward; re-seek earlier if the first decoded frame is after the target; sequential
  decode when the next target is close). RECENT: N = 9 targets evenly spaced over [max(0, t - 3), t]; HISTORY: N = 37
  over [0, t]. Asserted: every selected frame pts <= t. LANCZOS to 768x432, lossless PNG (compress_level 1); SHA-256 per
  frame. No frames are stored on disk; a small per-process LRU cache of encoded PNGs only.
PROMPT (one fixed template per dataset): header "The following are {N} frames from a video, in order from oldest to
  newest." + N images (separate, oldest first) + task text + instruction. Multiple-choice (OVO single-query, RTV):
  "Question: {question}\nOptions:\nA. {..}\n...\nAnswer with the option's letter from the given choices directly."
  OVO forward tasks have no options in the annotation: their task text is the UPSTREAM template (constant.py
  REC / SSR / CRR, filled as utils/OVOBench.build_prompt does) verbatim, with its own answer instruction (count /
  Yes / No) — the option-letter instruction cannot apply (recorded deviation). No timestamps or file names.
PARSERS: OVO single-query: upstream get_score (int(gt in response)); REC: upstream digits-join == count; SSR / CRR:
  upstream ("N"/"Y" exact, else gt "Yes"/"No" substring). RTV: upstream scripts/utils/prompt_utils.extract_pred_letter
  ("Unknown" = unparsed). Thinking: parsed on the text after </think> (no </think> => no answer). A strict parser is
  also applied to classify unparsed / ambiguous responses (reported separately).
"""
import base64
import collections
import hashlib
import io
import json
import random
import re
from pathlib import Path

DATA = Path("/home/pragya/data/datasets")
OVO_ANN = DATA / "ovo_bench/code/data/ovo_bench_new.json"
OVO_VID = DATA / "ovo_bench/src_videos/src_videos"
RTV_ANN = DATA / "rtv_bench/hf/QA.json"
RTV_VID = DATA / "rtv_bench/hf/videos"
SIZE = (768, 432)
PNG_LEVEL = 1
INPUTS = {"RECENT": 9, "HISTORY": 37}
FORWARD = ("REC", "SSR", "CRR")
HEADER = "The following are {n} frames from a video, in order from oldest to newest."
MC_INSTR = "Answer with the option's letter from the given choices directly."

# OVO-Bench constant.py templates (code @ c34093f9), read VERBATIM from the cloned file by parsing it with ast
# (string-literal assignments only; the upstream file is never executed).
def _upstream_templates():
    import ast
    tree = ast.parse((DATA / "ovo_bench/code/constant.py").read_text())
    lit = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for tg in node.targets:
                if isinstance(tg, ast.Name):
                    lit[tg.id] = node.value.value
    return lit["REC_PROMPT_TEMPLATE"], lit["SSR_PROMPT_TEMPLATE"], lit["CRR_PROMPT_TEMPLATE"]


OVO_REC, OVO_SSR, OVO_CRR = _upstream_templates()
OVO_CONSTANT_SHA256 = hashlib.sha256((DATA / "ovo_bench/code/constant.py").read_bytes()).hexdigest()


def mc_text(question, opts):
    return f"Question: {question}\nOptions:\n" + "\n".join(f"{k}. {v}" for k, v in opts) + f"\n{MC_INSTR}"


def build_items():
    items = []
    for e in json.load(open(OVO_ANN)):
        vid = str(OVO_VID / e["video"])
        if e["task"] not in FORWARD:
            opts = [(chr(65 + i), o) for i, o in enumerate(e["options"])]
            items.append(dict(item_id=f"ovo_{e['id']}", dataset="ovo_bench", part="ovo_other", task=e["task"],
                              video=vid, video_key=e["video"], t=float(e["realtime"]), text=mc_text(e["question"], opts),
                              n_options=len(opts), gt=chr(65 + e["gt"]), parser="ovo_mc",
                              letters=[k for k, _ in opts]))
        else:
            for j, ti in enumerate(e["test_info"]):
                if e["task"] == "REC":
                    text, gt, parser = OVO_REC.format("How many times did they " + e["activity"] + "?"), ti["count"], "ovo_rec"
                elif e["task"] == "SSR":
                    text, gt, parser = OVO_SSR.format(ti["step"]), ti["type"], "ovo_yn"
                else:
                    text, gt, parser = OVO_CRR.format(e["question"]), ti["type"], "ovo_yn"
                items.append(dict(item_id=f"ovo_{e['id']}_{j}", dataset="ovo_bench", part="ovo_forward",
                                  task=e["task"], video=vid, video_key=e["video"], t=float(ti["realtime"]), text=text,
                                  n_options=None, gt=gt, parser=parser, letters=None))
    for k, q in enumerate(json.load(open(RTV_ANN))):
        opts = sorted(q["options"].items())
        items.append(dict(item_id=f"rtv_{k:04d}_{q['questionID']}", dataset="rtv_bench", part="rtv", task=q["type"],
                          video=str(RTV_VID / q["field"] / q["video"]), video_key=f"{q['field']}/{q['video']}",
                          t=float(q["end_time"]), text=mc_text(q["question"], opts), n_options=len(opts),
                          gt=q["answer"], parser="rtv", letters=[k for k, _ in opts], options=dict(opts)))
    return items


def fixed_order(items, seed=0):
    """Seed-0 random order per dataset, stratified by task: shuffle within task, then place item i of a task with n
    items at key (i + u) / n (u ~ U(0,1) from the same rng) and sort — every prefix is ~proportional by task."""
    out = {}
    for ds in ("ovo_bench", "rtv_bench"):
        rng = random.Random(seed)
        by = collections.defaultdict(list)
        for it in items:
            if it["dataset"] == ds:
                by[it["task"]].append(it)
        keyed = []
        for task in sorted(by):
            lst = sorted(by[task], key=lambda x: x["item_id"])
            rng.shuffle(lst)
            for i, it in enumerate(lst):
                keyed.append(((i + rng.random()) / len(lst), it["item_id"], it))
        out[ds] = [it for _, _, it in sorted(keyed, key=lambda x: (x[0], x[1]))]
    return out


def targets(t, n_input):
    if n_input == 9:
        a = max(0.0, t - 3.0)
    else:
        a = 0.0
    return [a + k * (t - a) / (n_input - 1) for k in range(n_input)], t - a


SEEK_GAP = 4.0
_CACHE = collections.OrderedDict()
_CACHE_MAX = 256


def _encode(path, ts, fr):
    from PIL import Image
    key = (path, round(ts, 6))
    png = _CACHE.get(key)
    if png is None:
        im = Image.fromarray(fr.to_ndarray(format="rgb24")).resize(SIZE, Image.LANCZOS)
        b = io.BytesIO()
        im.save(b, format="PNG", compress_level=PNG_LEVEL)
        png = b.getvalue()
        _CACHE[key] = png
        if len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)
    else:
        _CACHE.move_to_end(key)
    return png


def select_frames(path, tgts, encode=True):
    """Latest decoded frame with pts <= target for each target. Returns [(pts, png bytes or None)] in target order.
    Frames are encoded while the container is open."""
    import av
    order = sorted(range(len(tgts)), key=lambda i: tgts[i])
    res = [None] * len(tgts)
    with av.open(path) as c:
        s = c.streams.video[0]
        s.thread_type = "AUTO"
        tb = s.time_base
        st = {"gen": None, "prev": None, "pend": None}

        def nxt():
            for fr in st["gen"]:
                if fr.pts is not None:
                    return fr
            return None

        def pts(fr):
            return float(fr.pts * tb)

        def seek_to(tg):
            back = 0.0
            while True:
                off = max(0.0, tg - back)
                c.seek(int(off / tb), stream=s, backward=True, any_frame=False)
                st["gen"] = c.decode(s)
                st["prev"], st["pend"] = None, nxt()
                if off == 0.0 or (st["pend"] is not None and pts(st["pend"]) <= tg + 1e-9):
                    return
                back = 2.0 if back == 0 else back * 2

        for i in order:
            tg = tgts[i]
            pend = st["pend"]
            if st["gen"] is None or (pend is not None and pts(pend) <= tg and tg - pts(pend) > SEEK_GAP):
                seek_to(tg)
            while st["pend"] is not None and pts(st["pend"]) <= tg + 1e-9:
                st["prev"] = st["pend"]
                st["pend"] = nxt()
            fr = st["prev"] if st["prev"] is not None else st["pend"]  # target before the first frame: first frame
            ts = pts(fr)
            res[i] = (ts, _encode(path, ts, fr) if encode else None)
    return res


def render(path, tgts):
    return [(ts, png, hashlib.sha256(png).hexdigest()) for ts, png in select_frames(path, tgts)]


def grey_png():
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", SIZE, (128, 128, 128)).save(b, format="PNG", compress_level=PNG_LEVEL)
    return b.getvalue()


def build_content(item, inp, grey=False):
    """User-turn content + frame log for one request (runs in a worker process)."""
    n = INPUTS[inp]
    tg, span = targets(item["t"], n)
    if grey:
        g = grey_png()
        frames = [(None, g, hashlib.sha256(g).hexdigest())] * n
    else:
        frames = render(item["video"], tg)
        assert all(ts <= item["t"] + 1e-6 for ts, _, _ in frames), (item["item_id"], inp)
    content = [{"type": "text", "text": HEADER.format(n=n)}]
    for _, png, _ in frames:
        content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}})
    content.append({"type": "text", "text": item["text"]})
    pts = [ts for ts, _, _ in frames]
    return content, dict(frame_pts=pts, frame_sha256=[h for _, _, h in frames], n_distinct=len(set(pts)),
                         span_s=span, short_span=(inp == "RECENT" and span < 3.0 - 1e-9),
                         before_first_frame=sum(1 for p, x in zip(pts, tg) if p is not None and p > x + 1e-9))


# ---------------- parsers ----------------
def answer_region(text, thinking):
    if text is None:
        return None
    if thinking:
        return text.split("</think>", 1)[1] if "</think>" in text else None
    return text


def upstream_correct(item, resp):
    """Upstream scorers, ported verbatim in behaviour."""
    if resp is None:
        return False
    p = item["parser"]
    if p == "ovo_mc":
        return item["gt"] in resp
    if p == "ovo_rec":
        return "".join(re.findall(r"\d+", resp)) == str(item["gt"])
    if p == "ovo_yn":
        if (resp == "N" and item["gt"] == 0) or (resp == "Y" and item["gt"] == 1):
            return True
        return ("No" if item["gt"] == 0 else "Yes") in resp
    if p == "rtv":
        return rtv_extract(resp, item["options"]) == item["gt"]
    raise ValueError(p)


def rtv_extract(text, options):
    """RTV-Bench scripts/utils/prompt_utils.extract_pred_letter, verbatim in behaviour."""
    if not text:
        return "Unknown"
    valid = set(k.upper() for k in options.keys())
    m = re.search(r"\b([A-Z])\b", text.upper())
    if m and m.group(1) in valid:
        return m.group(1)
    m = re.search(r"(OPTION|ANSWER)\s*[:\-]?\s*([A-Z])", text.upper())
    if m and m.group(2) in valid:
        return m.group(2)
    c0 = text.strip()[:1].upper()
    if c0 in valid:
        return c0
    return "Unknown"


def strict_parse(item, resp):
    """Strict: exactly one valid answer token; ambiguous (several distinct candidates) or none => unparsed."""
    if resp is None:
        return None, "no_answer_region"
    s = resp.strip()
    if not s:
        return None, "empty"
    p = item["parser"]
    if p in ("ovo_mc", "rtv"):
        c = set(re.findall(r"(?<![A-Za-z])([A-Z])(?![A-Za-z])", s)) & set(item["letters"])
        return (c.pop(), "ok") if len(c) == 1 else (None, "ambiguous" if c else "unparsed")
    if p == "ovo_rec":
        c = set(re.findall(r"\d+", s))
        return (c.pop(), "ok") if len(c) == 1 else (None, "ambiguous" if c else "unparsed")
    c = set(w.lower() for w in re.findall(r"\b(yes|no)\b", s, re.I))
    return (c.pop().capitalize(), "ok") if len(c) == 1 else (None, "ambiguous" if c else "unparsed")


def guess_floor(item):
    if item["parser"] in ("ovo_mc", "rtv"):
        return 1.0 / item["n_options"]
    if item["parser"] == "ovo_yn":
        return 0.5
    return None  # REC count: no finite option set
