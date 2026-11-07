import csv, glob, json, os, re, collections
from pathlib import Path

ROOT = Path("/mnt/ssd/hf_models/datasets")

# Temporal-field question asked by the task, answered with FIELD NAMES ONLY.
FIELDS = ["query_timestamp", "answer_timestamp", "evidence_interval",
          "event_onset", "multi_answer_over_time", "task_category"]


def rtv():
    q = json.load(open(ROOT / "rtv_bench/hf/QA.json"))
    vids = {x["video"] for x in q}
    return dict(
        questions=len(q), unique_videos=len(vids), video_ids=vids,
        schema=sorted(q[0].keys()),
        examples={t: next(x for x in q if x["type"] == t)
                  for t in sorted({x["type"] for x in q})},
        temporal={
            "query_timestamp": None,
            "answer_timestamp": None,
            "evidence_interval": "start_time + end_time",
            "event_onset": None,
            "multi_answer_over_time": None,
            "task_category": "type (+ field)",
        },
        claims={"videos": "552", "questions": "4,631 (paper) / 4,608 (README)"})


def ovo():
    o = json.load(open(ROOT / "ovo_bench/code/data/ovo_bench_new.json"))
    BACK = {'EPM','HLD','ASI','STU','OJR','ATR','ACR','OCR','FPD'}
    FWD = {'REC','SSR','CRR'}
    sub = sum(len(x.get("test_info", [])) for x in o if x["task"] in FWD)
    nb = sum(1 for x in o if x["task"] in BACK)
    vids = {x["video"] for x in o}
    return dict(
        questions=nb + sub, entries=len(o), backward_entries=nb,
        forward_subqueries=sub, unique_videos=len(vids), video_ids=vids,
        schema={t: sorted(next(x for x in o if x["task"] == t).keys())
                for t in sorted({x["task"] for x in o})},
        examples={t: next(x for x in o if x["task"] == t)
                  for t in sorted({x["task"] for x in o})},
        temporal={
            "query_timestamp": "realtime (backward); test_info[].realtime (REC/SSR); ask_time (CRR)",
            "answer_timestamp": None,
            "evidence_interval": "start_times/end_times (REC); start_time/end_time (SSR); clue_time (CRR)",
            "event_onset": "start_times (REC); start_time (SSR)",
            "multi_answer_over_time": "test_info[] (REC/SSR/CRR)",
            "task_category": "task",
        },
        claims={"videos": "644", "questions": "2,814 (paper) / 3,100 (README)"})


def her():
    d = ROOT / "herbench/hf/data"
    a = json.load(open(d / "herbench_annotations.json"))
    lite = json.load(open(d / "herbench_annotations_lite.json"))
    lv2 = json.load(open(d / "herbench_annotations_lite_v2.json"))
    vm = json.load(open(d / "video_metadata.json"))
    vids = {x["video_id"] for x in a}
    return dict(
        questions=len(a), unique_videos=len(vids), video_ids={x["video_path"] for x in a},
        lite_questions=len(lite), lite_videos=len({x["video_id"] for x in lite}),
        lite_v2_questions=len(lv2), lite_v2_videos=len({x["video_id"] for x in lv2}),
        metadata_videos=len(vm["videos"]), metadata_summary=vm["summary"],
        schema=sorted(a[0].keys()),
        examples={t: next(x for x in a if x["task_type"] == t)
                  for t in sorted({x["task_type"] for x in a})},
        temporal={
            "query_timestamp": None,
            "answer_timestamp": None,
            "evidence_interval": "metadata.required_timestamps / metadata.timestamps",
            "event_onset": "metadata.required_timestamps (point form, e.g. '3:20:910')",
            "multi_answer_over_time": None,
            "task_category": "task_type",
        },
        claims={"videos": "335 (README) / 337 (CITATION.cff)",
                "questions": "27,936 (README) / 26,806 (CITATION.cff)",
                "lite": "5,960", "lite_v2": "1,971 over 68 videos"})


def sb():
    base = ROOT / "streaming_bench/hf/StreamingBench"
    per = {}
    allv = set()
    total = 0
    examples = {}
    schema = {}
    for p in sorted(glob.glob(f"{base}/*.csv")):
        b = os.path.basename(p)
        rows = list(csv.DictReader(open(p)))
        vids = {re.sub(r'_\d+$', '', r["question_id"]) for r in rows}
        per[b] = {"rows": len(rows), "videos": len(vids)}
        schema[b] = list(rows[0].keys())
        for t in sorted({r["task_type"] for r in rows}):
            examples.setdefault(t, next(r for r in rows if r["task_type"] == t))
        if b != "Proactive_Output_50.csv":
            total += len(rows)
            allv |= vids
    return dict(
        questions=total, unique_videos=len(allv), video_ids=allv, per_file=per,
        schema=schema, examples=examples,
        temporal={
            "query_timestamp": "time_stamp",
            "answer_timestamp": "ground_truth_time_stamp (Proactive_Output only)",
            "evidence_interval": None,
            "event_onset": "ground_truth_time_stamp (Proactive_Output only)",
            "multi_answer_over_time": None,
            "task_category": "task_type (+ temporal_clue_type, frames_required)",
        },
        claims={"videos": "900", "questions": "4,500"})


if __name__ == "__main__":
    out = {"rtv_bench": rtv(), "ovo_bench": ovo(), "herbench": her(), "streaming_bench": sb()}
    for k, v in out.items():
        print(f"\n===== {k} =====")
        print(f"  questions={v['questions']}  unique_videos={v['unique_videos']}")
        print(f"  upstream claims: {v['claims']}")
        print("  temporal fields present:")
        for f in FIELDS:
            val = v["temporal"][f]
            print(f"    {f:24s} {'YES  ' + val if val else 'NO'}")
    ser = {k: {kk: (sorted(vv) if isinstance(vv, set) else vv)
               for kk, vv in v.items()} for k, v in out.items()}
    json.dump(ser, open(ROOT / "annotations_report.json", "w"), indent=1, default=str)
    print("\nwrote", ROOT / "annotations_report.json")
