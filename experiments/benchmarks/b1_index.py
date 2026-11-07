"""StudyB1-flash: build the per-question work index.

Query-time field per dataset is taken from the cited sources recorded in
results/datasets/temporal_field_semantics.json (see reports/dataset_download.md s2).
Nothing here is inferred from a field name.

  RTV-Bench      t = end_time              (video_utils.py:177-187; infer_model_rtv.py:101,107)
  OVO-Bench      t = realtime              (utils/chunk_videos.py:30,39; utils/OVOBench.py:30,62)
                 forward tasks: t = test_info[i].realtime, one row per probe
                                (chunk_videos.py:46,56; OVOBench.py:93-105)
  StreamingBench t = time_stamp            (StreamingBench.py:41-50; video_execution.py:4,23-25)
  HERBench       no query time -> whole video; required_timestamps is UNKNOWN and is
                 carried through for offline analysis only, never used at runtime.
"""
from __future__ import annotations

import csv
import json
import os
import random
import sys
from pathlib import Path

R = Path("/mnt/ssd/hf_models/datasets")
OUT = Path("/home/pragya/Desktop/FM-switching/results/benchmarks/study_b1_flash/index")

SB_INCLUDE = {
    "Contextual_Understanding.csv",
    "Real_Time_Visual_Understanding.csv",
    "Sequential_Question_Answering.csv",
}
SB_SKIP_AUDIO = {"Omni_Source_Understanding.csv"}
SB_SKIP_PROACTIVE = {"Proactive_Output.csv", "Proactive_Output_50.csv"}
SB_QID_PREFIX_TO_DIR = {
    "Misleading Context Recognition": "Misleading Context Understanding",
    "Anomaly Context Understanding": "Anomaly Context Understanding",
    "Real-Time Visual Understanding": "Real-Time Visual Understanding",
    "Sequential_Question_Answering": "Sequential Question Answering",
}

OVO_BACKWARD = {"EPM", "ASI", "HLD"}
OVO_REALTIME = {"OCR", "ACR", "ATR", "STU", "FPD", "OJR"}
OVO_FORWARD = {"REC", "SSR", "CRR"}


def hms(s: str) -> float:
    return float(sum(int(x) * 60**i for i, x in enumerate(reversed(str(s).split(":")))))


def rtv():
    rows = []
    for q in json.load(open(R / "rtv_bench/hf/QA.json")):
        vp = R / "rtv_bench/hf/videos" / q["field"] / q["video"]
        rows.append(dict(
            dataset="rtv_bench", task=q["type"], qid=q["questionID"],
            video=str(vp), video_key=f'{q["field"]}/{q["video"]}',
            t=float(q["end_time"]), t_field="end_time", mode_set=["RECENT", "HISTORY"],
            question=q["question"], options=dict(q["options"]),
            gold=q["answer"], answer_kind="letter", parser="rtv_extract_pred_letter",
        ))
    return rows


def ovo():
    rows = []
    for e in json.load(open(R / "ovo_bench/code/data/ovo_bench_new.json")):
        vp = R / "ovo_bench/src_videos/src_videos" / e["video"]
        task = e["task"]
        base = dict(dataset="ovo_bench", task=task, video=str(vp), video_key=e["video"],
                    mode_set=["RECENT", "HISTORY"], parser="ovo_upstream")
        if task in OVO_BACKWARD | OVO_REALTIME:
            opts = {chr(65 + i): o for i, o in enumerate(e["options"])}
            rows.append(dict(base, qid=f'ovo-{e["id"]}', t=float(e["realtime"]),
                             t_field="realtime", question=e["question"], options=opts,
                             gold=chr(65 + e["gt"]), answer_kind="letter",
                             ovo_group="backward" if task in OVO_BACKWARD else "realtime"))
        elif task in OVO_FORWARD:
            for i, ti in enumerate(e["test_info"]):
                if task == "REC":
                    q = "How many times did they " + e["activity"] + "?"
                    gold, kind = str(ti["count"]), "count"
                elif task == "SSR":
                    q = ti["step"]
                    gold, kind = ("No" if ti["type"] == 0 else "Yes"), "yesno"
                else:
                    q = e["question"]
                    gold, kind = ("No" if ti["type"] == 0 else "Yes"), "yesno"
                rows.append(dict(base, qid=f'ovo-{e["id"]}-{i}', t=float(ti["realtime"]),
                                 t_field="test_info[].realtime", question=q, options=None,
                                 gold=gold, answer_kind=kind, ovo_group="forward"))
        else:
            raise SystemExit(f"unknown OVO task {task}")
    return rows


def herbench():
    lite = {q["question_id"] for q in
            json.load(open(R / "herbench/hf/data/herbench_annotations_lite_v2.json"))}
    rows = []
    for q in json.load(open(R / "herbench/hf/data/herbench_annotations.json")):
        rel = q["video_path"]
        rel = rel[len("videos/"):] if rel.startswith("videos/") else rel
        vp = R / "herbench/extracted_full" / rel
        opts = {}
        for c in q["choices"]:
            if len(c) > 2 and c[1] == "." and c[0].isalpha():
                opts[c[0].upper()] = c[2:].strip()
            else:
                opts[chr(65 + len(opts))] = c
        rows.append(dict(
            dataset="herbench", task=q["task_type"], qid=q["question_id"],
            video=str(vp), video_key=rel,
            t=None, t_field="none (whole video; no query time in this benchmark)",
            mode_set=["HISTORY"],
            question=q["question"], options=opts, gold=q["answer"],
            answer_kind="letter", parser="herbench_extract_answer_choice",
            lite_v2=q["question_id"] in lite,
            required_timestamps=(q.get("metadata") or {}).get("timestamps_required")
            or (q.get("metadata") or {}).get("required_timestamps"),
            video_exists=vp.exists(),
        ))
    return rows


def streaming():
    rows, skipped = [], {}
    d = R / "streaming_bench/hf/StreamingBench"
    for f in sorted(os.listdir(d)):
        if not f.endswith(".csv"):
            continue
        n = len(list(csv.DictReader(open(d / f))))
        if f in SB_SKIP_AUDIO:
            skipped[f] = dict(rows=n, reason="requires audio by upstream definition "
                              "(README.md:39 'integrate visual and audio inputs')")
            continue
        if f in SB_SKIP_PROACTIVE:
            skipped[f] = dict(rows=n, reason="upstream scoring cannot be applied unchanged "
                              "(StreamingBenchProactive.py:35-50 polls the model once per second "
                              "to ground_truth_time_stamp+4; count.py:43-57 needs dialog_history "
                              "times and scores a hit within +/-2 s) AND needs video after the "
                              "query time (ground_truth_time_stamp > time_stamp)")
            continue
        if f not in SB_INCLUDE:
            skipped[f] = dict(rows=n, reason="not in include set")
            continue
        for r in csv.DictReader(open(d / f)):
            qid = r["question_id"]
            pre, _, rest = qid.rpartition("_")
            pre2, _, sample = pre.rpartition("_")
            sample_dir = f"{pre2.rsplit('_', 1)[-1]}_{sample}" if False else None
            # question_id is "<prefix>_sample_<N>_<idx>"
            import re as _re
            m = _re.match(r"^(.*)_(sample_\d+)_(\d+)$", qid)
            if not m:
                raise SystemExit(f"unparsed question_id {qid}")
            prefix, sdir = m.group(1), m.group(2)
            tdir = SB_QID_PREFIX_TO_DIR[prefix]
            vp = R / "streaming_bench/extracted_by_task" / tdir / sdir / "video.mp4"
            raw = r["options"]
            try:
                opt_list = json.loads(raw.replace("'", '"')) if raw.strip().startswith("[") else None
            except Exception:
                opt_list = None
            if opt_list is None:
                import ast
                opt_list = ast.literal_eval(raw)
            opts = {}
            for i, o in enumerate(opt_list):
                o = str(o).strip()
                if len(o) > 2 and o[1] == "." and o[0].isalpha():
                    opts[o[0].upper()] = o[2:].strip()
                else:
                    opts[chr(65 + i)] = o
            rows.append(dict(
                dataset="streaming_bench", task=r["task_type"], qid=qid,
                video=str(vp), video_key=f"{tdir}/{sdir}",
                t=hms(r["time_stamp"]), t_field="time_stamp",
                mode_set=["RECENT", "HISTORY"],
                question=r["question"], options=opts, gold=r["answer"].strip().upper(),
                answer_kind="letter", parser="streamingbench_first_char",
                sb_file=f, temporal_clue_type=r.get("temporal_clue_type"),
                video_exists=vp.exists(),
            ))
    return rows, skipped


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sb, sb_skipped = streaming()
    sets = {"rtv_bench": rtv(), "ovo_bench": ovo(), "herbench": herbench(), "streaming_bench": sb}
    summary = {"skipped": {"streaming_bench": sb_skipped}, "datasets": {}}

    for name, rows in sets.items():
        missing = [r for r in rows if not Path(r["video"]).exists()]
        rows = [r for r in rows if Path(r["video"]).exists()]
        # fixed seed-0 order, stratified by task (round-robin over tasks)
        rnd = random.Random(0)
        by_task: dict[str, list] = {}
        for r in rows:
            by_task.setdefault(r["task"], []).append(r)
        for k in by_task:
            by_task[k].sort(key=lambda r: r["qid"])
            rnd.shuffle(by_task[k])
        order, keys = [], sorted(by_task)
        idx = {k: 0 for k in keys}
        while len(order) < len(rows):
            for k in keys:
                if idx[k] < len(by_task[k]):
                    order.append(by_task[k][idx[k]])
                    idx[k] += 1
        for i, r in enumerate(order):
            r["order"] = i
        with open(OUT / f"{name}.jsonl", "w") as fh:
            for r in order:
                fh.write(json.dumps(r) + "\n")
        summary["datasets"][name] = {
            "rows": len(order), "videos": len({r["video_key"] for r in order}),
            "tasks": {k: len(v) for k, v in sorted(by_task.items())},
            "dropped_missing_video": len(missing),
            "dropped_qids_sample": [r["qid"] for r in missing[:10]],
        }
        if name == "herbench":
            summary["datasets"][name]["lite_v2_rows"] = sum(1 for r in order if r["lite_v2"])
    json.dump(summary, open(OUT / "index_summary.json", "w"), indent=1)
    print(json.dumps(summary, indent=1)[:4000])


if __name__ == "__main__":
    main()
