#!/usr/bin/env python3
"""StudyB2 StreamingBench adapter (HF mjuicem/StreamingBench @48872fa7, code THUNLP-MT/StreamingBench @89299232).

Items: the multiple-choice CSVs in hf/StreamingBench/ except
  - Omni_Source_Understanding.csv (1,000 q): requires audio by upstream definition (README.md:39 "integrate visual and
    audio inputs"); NOT RUN, listed.
  - Proactive_Output.csv (250) + Proactive_Output_50.csv (50): upstream scoring cannot be applied unchanged
    (src/benchmark/StreamingBenchProactive.py polls the model once per second up to ground_truth_time_stamp + 4;
    src/data/count.py:43-57 scores the time of the output within +/-2 s) and it needs video after the query time;
    NOT RUN, listed.
  => Real_Time_Visual_Understanding (2,500) + Contextual_Understanding (500) + Sequential_Question_Answering (250) = 3,250.
Query time t = time_stamp (HH:MM:SS -> seconds), as src/benchmark/StreamingBench.py:41-50 converts it and
src/utils/video_execution.py:4,23-25 cuts the clip [0, t] (time_start = 0 with no context window). Same definition as
flash (results/datasets/temporal_field_semantics.json).
Options: the CSV list ("A. ..."); per option, a "<letter>." prefix gives the letter, otherwise the letter is its
position (flash's b1_index.py rule, so annotations match flash exactly; upstream StreamingBench.py:55-56 only adds
letters when the FIRST option lacks "A."). Anomaly: Sequential_Question_Answering_sample_14_1 has options
['A.Lebrun.', 'Fan Z.D.', 'Xu xin.', 'Ma Lin.'] (a name starting "A."), which becomes A "Lebrun.", B, C, D; and
Sequential_Question_Answering_sample_41_5 is lettered A, B, B, D upstream (gold A): the prompt shows the four options
verbatim, the strict parser's letter set is {A, B, D}, the floor is 1/4 (four options shown). Template: StudyB1's fixed template (b1_common.HEADER + b1_common.mc_text, i.e. header,
"Question:", "Options:", lettered options, "Answer with the option's letter from the given choices directly.").
Upstream scorer (src/data/count.py:65-72): model_answer = response[0]; correct iff model_answer == answer; empty
responses are dropped from upstream's denominator (here: counted WRONG and reported separately).
  Recorded deviation: the answer region is left-stripped of whitespace before taking its first character (a Thinking
  answer region begins with "\\n\\n" after </think>; upstream never saw a reasoning model). Case is NOT changed.
Strict scorer: exactly one standalone option letter in the answer region (as StudyB1 strict).
Video: /home/pragya/data/datasets/streaming_bench/extracted_by_task/<task dir>/<sample_N>/video.mp4 (flash's layout).
Shards by upstream archive (disk): shard 1 = Sequential QA (2 zips), Anomaly, Misleading, Real-Time 1-150 and 201-250;
shard 2 = Real-Time 151-200, 251-350; shard 3 = Real-Time 351-500.
Order: seed-0 random order stratified by task over all 3,250 questions (b1_common.fixed_order's algorithm); a shard runs
its own questions in that order. Grey: the first 100 questions of that order, with shard 1.
"""
import ast
import collections
import csv
import random
import re
from pathlib import Path

DATA = Path("/home/pragya/data/datasets/streaming_bench")
CSV_DIR = DATA / "hf/StreamingBench"
VID = DATA / "extracted_by_task"
INCLUDE = {"Real_Time_Visual_Understanding.csv": "sb_realtime", "Contextual_Understanding.csv": "sb_contextual",
           "Sequential_Question_Answering.csv": "sb_sequential"}
SKIPPED = {"Omni_Source_Understanding.csv": "requires audio by upstream definition (README.md:39 'integrate visual "
                                            "and audio inputs')",
           "Proactive_Output.csv": "upstream scoring cannot be applied unchanged (StreamingBenchProactive.py polls to "
                                   "ground_truth_time_stamp + 4; count.py:43-57 scores output time within +/-2 s) and "
                                   "needs video after the query time",
           "Proactive_Output_50.csv": "same as Proactive_Output.csv"}
QID_PREFIX_TO_DIR = {"Misleading Context Recognition": "Misleading Context Understanding",
                     "Anomaly Context Understanding": "Anomaly Context Understanding",
                     "Real-Time Visual Understanding": "Real-Time Visual Understanding",
                     "Sequential_Question_Answering": "Sequential Question Answering"}
ARCHIVES = {1: ["Sequential Question Answering_1-25.zip", "Sequential Question Answering_26-50.zip",
                "Anomaly Context Understanding.zip", "Misleading Context Understanding.zip",
                "Real-Time Visual Understanding_1-50.zip", "Real-Time Visual Understanding_51-100.zip",
                "Real-Time Visual Understanding_101-150.zip", "Real-Time Visual Understanding_201-250.zip"],
            2: ["Real-Time Visual Understanding_151-200.zip", "Real-Time Visual Understanding_251-300.zip",
                "Real-Time Visual Understanding_301-350.zip"],
            3: ["Real-Time Visual Understanding_351-400.zip", "Real-Time Visual Understanding_401-450.zip",
                "Real-Time Visual Understanding_451-500.zip"]}
ARCHIVE_DIR = {z: re.sub(r"_\d+-\d+$", "", z[:-4]) for zs in ARCHIVES.values() for z in zs}  # zip -> task dir


def hms(s):
    return float(sum(int(x) * 60 ** i for i, x in enumerate(reversed(str(s).strip().split(":")))))


def shard_of(task_dir, sample):
    n = int(sample.split("_")[1])
    if task_dir != "Real-Time Visual Understanding":
        return 1
    if n <= 150 or 201 <= n <= 250:
        return 1
    if 151 <= n <= 200 or 251 <= n <= 350:
        return 2
    return 3


def build_items():
    import b1_common as B
    items = []
    for f, part in INCLUDE.items():
        for r in csv.DictReader(open(CSV_DIR / f)):
            qid = r["question_id"]
            m = re.match(r"^(.*)_(sample_\d+)_(\d+)$", qid)
            if not m:
                raise SystemExit(f"unparsed question_id {qid}")
            tdir, sdir = QID_PREFIX_TO_DIR[m.group(1)], m.group(2)
            raw = ast.literal_eval(r["options"])
            opts = []   # flash's per-option rule (b1_index.py), so the annotations match flash's index exactly
            for i, o in enumerate(raw):
                o = str(o).strip()
                if len(o) > 2 and o[1] == "." and o[0].isalpha():
                    opts.append((o[0].upper(), o[2:].strip()))
                else:
                    opts.append((chr(65 + i), o))
            items.append(dict(item_id=f"sb_{qid}", qid=qid, dataset="streaming_bench", part=part, task=r["task_type"],
                              video=str(VID / tdir / sdir / "video.mp4"), video_key=f"{tdir}/{sdir}",
                              t=hms(r["time_stamp"]), time_stamp=r["time_stamp"], text=B.mc_text(r["question"], opts),
                              question=r["question"], options=dict(opts), n_options=len(opts),
                              gt=r["answer"].strip(), parser="sb_first_char", letters=list(dict.fromkeys(k for k, _ in opts)),
                              sb_file=f, temporal_clue_type=r.get("temporal_clue_type"),
                              frames_required=r.get("frames_required"), shard=shard_of(tdir, sdir)))
    return items


def fixed_order(items, seed=0):
    """b1_common.fixed_order's algorithm for one dataset."""
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


def upstream_correct(item, resp):
    if not resp:
        return False
    s = resp.lstrip()
    return bool(s) and s[0] == item["gt"]


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
