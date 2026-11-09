#!/usr/bin/env python3
"""StudyB2 HERBench adapter (HF DanBenAmi/HERBench @30b42e97, code DanBenAmi/HERBench @fe66f377).

Sets:
  lite_v2 : data/herbench_annotations_lite_v2.json (1,971 q, 68 videos), item ids "herL_<qid>".
  full    : data/herbench_annotations.json (27,631 q, 335 videos referenced, 334 on disk upstream), item ids "her_<qid>".
  Lite-v2 is a revised set, NOT a subset: 1,429 of its question_ids also occur in the full set and only 736 of those are
  identical (question, choices, answer, video); 542 ids are Lite-v2 only. Full-set questions identical to a Lite-v2 question
  are NOT run twice: their Lite-v2 rows stand for them (`duplicate_of`).
No query time in this benchmark: t = the video's duration (first video stream, flash's ffprobe.jsonl), HISTORY only
(37 frames over [0, t]); every frame <= t (b1_common asserts). required_timestamps (question metadata) is carried in
the item and written to every row for offline analysis; it is NEVER used at runtime.
Questions whose video is absent upstream (65 full-set questions, one video; flash's crosscheck) cannot be run: listed.
Options: "choices" ("A. ..."; a "<letter>." prefix gives the letter, else its position: flash's rule). Template:
StudyB1's fixed template (b1_common.mc_text). Upstream scorer: evaluation/model_wrappers/base_vlm.py:263-315
(extract_answer_choice), ported verbatim below; 'ERROR' / no match = wrong. Thinking: scored after </think>.
Strict scorer: exactly one standalone option letter.
Shards (disk): shard 0 = the 68 Lite-v2 videos (all Lite-v2 questions + full-set questions on those videos);
shards 1.. = the remaining videos in a seed-0 random order, packed in that order up to SHARD_GIB (16) GiB of video bytes
(the 17 tar parts, 159 GiB, must stay on disk until the last shard; the floor is 20 GiB).
Order within a shard: seed-0 random order stratified by task (b1_common.fixed_order's algorithm). Grey: the first 100
questions of the full set's fixed order (shard 0).
"""
import collections
import json
import random
import re
from pathlib import Path

DATA = Path("/home/pragya/data/datasets/herbench")
ANN = DATA / "hf/data/herbench_annotations.json"
ANN_LITE = DATA / "hf/data/herbench_annotations_lite_v2.json"
VID = DATA / "extracted_full"
FFPROBE = DATA / "ffprobe.jsonl"            # flash's, pulled with the dataset
FLASH_ROOT = "/mnt/ssd/hf_models/datasets/herbench/extracted_full/"
SHARD_GIB = 16.0   # disk: all 17 tar parts (159 GiB) stay until the last shard; floor 20 GiB


def _rel(video_path):
    return video_path[len("videos/"):] if video_path.startswith("videos/") else video_path


def _probe():
    out = {}
    for l in open(FFPROBE):
        r = json.loads(l)
        out[r["path"].replace(FLASH_ROOT, "")] = r
    return out


def _item(q, kind, probe):
    import b1_common as B
    rel = _rel(q["video_path"])
    opts = []
    for i, c in enumerate(q["choices"]):
        c = str(c).strip()
        if len(c) > 2 and c[1] == "." and c[0].isalpha():
            opts.append((c[0].upper(), c[2:].strip()))
        else:
            opts.append((chr(65 + i), c))
    p = probe.get(rel)
    meta = q.get("metadata") or {}
    return dict(item_id=("herL_" if kind == "lite_v2" else "her_") + q["question_id"], qid=q["question_id"],
                set=kind, dataset="herbench", part="her_" + kind, task=q["task_type"], video=str(VID / rel),
                video_key=rel, t=float(p["duration"]) if p and p.get("duration") else None,
                video_bytes=p["size"] if p else None, runnable=bool(p and p.get("ok") and p.get("duration")),
                text=B.mc_text(q["question"], opts), question=q["question"], options=dict(opts),
                n_options=len(opts), letters=list(dict.fromkeys(k for k, _ in opts)), gt=str(q["answer"]).strip(),
                parser="her_extract",
                row_meta=dict(required_timestamps=meta.get("timestamps_required") or meta.get("required_timestamps"),
                              source_dataset=meta.get("source_dataset") or q.get("source_dataset")))


def build_items():
    probe = _probe()
    lite = [_item(q, "lite_v2", probe) for q in json.load(open(ANN_LITE))]
    full = [_item(q, "full", probe) for q in json.load(open(ANN))]
    key = lambda it: (it["question"], tuple(sorted(it["options"].items())), it["gt"], it["video_key"])
    lk = {key(it): it["item_id"] for it in lite}
    for it in full:
        it["duplicate_of"] = lk.get(key(it))
    lite_videos = sorted({it["video_key"] for it in lite})
    rest = sorted({it["video_key"] for it in full if it["runnable"]} - set(lite_videos))
    random.Random(0).shuffle(rest)
    size = {it["video_key"]: it["video_bytes"] or 0 for it in full + lite}
    shard_of = {v: 0 for v in lite_videos}
    k, acc = 1, 0
    for v in rest:
        if acc and acc + size[v] > SHARD_GIB * 2 ** 30:
            k, acc = k + 1, 0
        shard_of[v] = k
        acc += size[v]
    for it in lite + full:
        it["shard"] = shard_of.get(it["video_key"])
    return lite + full


def fixed_order(items, seed=0):
    rng = random.Random(seed)
    by = collections.defaultdict(list)
    for it in items:
        by[it["task"]].append(it)
    keyed = []
    for task in sorted(by):
        lst = sorted(by[task], key=lambda x: x["item_id"])
        rng.shuffle(lst)
        for i, it in enumerate(lst):
            keyed.append(((i + rng.random()) / len(lst), it["item_id"], it))
    return [it for _, _, it in sorted(keyed, key=lambda x: (x[0], x[1]))]


def extract_answer_choice(response):
    """HERBench evaluation/model_wrappers/base_vlm.py extract_answer_choice, verbatim in behaviour."""
    response = response.strip()
    if "ERROR" in response.upper() or not response:
        return "ERROR"
    patterns = [r"^([A-E])[\s\.\,\)]", r"^\(([A-E])\)", r"^([A-E])$", r"[Aa]nswer:\s*([A-E])\b",
                r"[Cc]hoice:\s*([A-E])\b", r"\b([A-E])\b[\.\,]"]
    for pattern in patterns:
        m = re.search(pattern, response)
        if m:
            return m.group(1).upper()
    up = response.upper()
    for m in re.finditer(r"([A-E])", up):
        a, b = m.start(1), m.end(1)
        before = up[a - 1] if a > 0 else " "
        after = up[b] if b < len(up) else " "
        if not before.isalpha() and not after.isalpha():
            return m.group(1)
    return "ERROR"


def upstream_correct(item, resp):
    if resp is None:
        return False
    return extract_answer_choice(resp) == item["gt"]


def strict_parse(item, resp):
    if resp is None:
        return None, "no_answer_region"
    s = resp.strip()
    if not s:
        return None, "empty"
    c = set(re.findall(r"(?<![A-Za-z])([A-Z])(?![A-Za-z])", s)) & set(item["letters"])
    return (c.pop(), "ok") if len(c) == 1 else (None, "ambiguous" if c else "unparsed")


def guess_floor(item):
    return 1.0 / item["n_options"]
