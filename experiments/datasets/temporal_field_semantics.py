"""Structural checks on benchmark annotation files (StudyDataDownload follow-up).

Annotation files only: no video decoding, no model, no GPU. Every claimed MEANING
carries a source (code path + line, README line, or paper section); where no source
settles it the value is the literal string UNKNOWN.
"""
import collections, csv, glob, json, os, re
from pathlib import Path

DATA = Path("/mnt/ssd/hf_models/datasets")
OUT = Path("/home/pragya/Desktop/FM-switching/results/datasets/temporal_field_semantics.json")
UNKNOWN = "UNKNOWN"


def norm(s):
    return re.sub(r"\s+", " ", s.strip().lower())


# --------------------------------------------------------------- RTV-Bench
def rtv():
    q = json.load(open(DATA / "rtv_bench/hf/QA.json"))
    pat = re.compile(r"^q-group-([a-z0-9]+)-(\d+)-(.+)$")
    m = [pat.match(x["questionID"]) for x in q]

    by_text = collections.defaultdict(list)
    for x in q:
        by_text[(x["video"], norm(x["question"]))].append(x)
    multi = {k: v for k, v in by_text.items() if len(v) > 1}
    changed = {k: v for k, v in multi.items() if len({y["answer"] for y in v}) > 1}

    by_id = collections.defaultdict(list)
    for x, z in zip(q, m):
        by_id[z.group(1)].append(x)
    imulti = {k: v for k, v in by_id.items() if len(v) > 1}
    ichanged = {k: v for k, v in imulti.items() if len({y["answer"] for y in v}) > 1}

    examples = []
    for k in list(ichanged)[:3]:
        rows = sorted(by_id[k], key=lambda x: x["end_time"])
        examples.append({"group": f"q-group-{k}", "video": rows[0]["video"],
                         "type": rows[0]["type"],
                         "rows": [{"questionID": r["questionID"], "end_time": r["end_time"],
                                   "question": r["question"], "options": r["options"],
                                   "answer": r["answer"]} for r in rows]})
    return {
        "n_questions": len(q), "n_videos": len({x["video"] for x in q}),
        "recurrence_by_video_and_question_text": {
            "groups": len(by_text), "groups_gt1_row": len(multi),
            "groups_where_answer_changes": len(changed),
            "rows_per_group": dict(sorted(collections.Counter(len(v) for v in by_text.values()).items()))},
        "recurrence_by_questionID_group_token": {
            "id_groups": len(by_id), "groups_gt1_row": len(imulti),
            "groups_where_answer_changes": len(ichanged),
            "rows_per_group": dict(sorted(collections.Counter(len(v) for v in by_id.values()).items())),
            "id_groups_spanning_more_than_one_video":
                sum(1 for v in by_id.values() if len({y["video"] for y in v}) > 1),
            "id_format": "q-group-<token>-<question_index>-option<N>"},
        "start_time": {
            "distinct_values": sorted({x["start_time"] for x in q}),
            "meaning": "constant 0 in every row; carries no per-question information. "
                       "Used only by scripts/data_preparation/prepare_rtv_clips.py:128-157 "
                       "(an optional clip-prep path), never by the eval path.",
            "source": "data: 4608/4608 rows have start_time==0; "
                      "scripts/infer/infer_model_rtv.py:101,107 passes only end_time"},
        "end_time": {
            "meaning": "query timestamp: the point in the stream at which the question is "
                       "asked. The clip handed to the model is [0, end_time].",
            "source": "scripts/utils/video_utils.py:177-187 crop_video_ffmpeg runs "
                      "ffmpeg -ss 0 -t <end_time>; called at scripts/infer/infer_model_rtv.py:101,107 "
                      "with end_time=float(sample['end_time']); README.md:122-127 "
                      "'evaluation operates on video clips ... split according to the provided timestamps'"},
        "multi_answer_over_time": {
            "verdict": "PRESENT",
            "source": "README.md:38 'Multi-Timestamp Question Answering: answers evolve as "
                      "video content changes over time'; plus the recurrence counts above"},
        "examples": examples,
    }


# --------------------------------------------------------------- OVO-Bench
def ovo():
    o = json.load(open(DATA / "ovo_bench/code/data/ovo_bench_new.json"))
    BACK = {"EPM", "HLD", "ASI", "STU", "OJR", "ATR", "ACR", "OCR", "FPD"}
    tasks = sorted({x["task"] for x in o})
    fields = ["realtime", "ask_time", "clue_time", "start_times", "end_times",
              "start_time", "end_time", "test_info"]
    per_task = {}
    for t in tasks:
        rows = [x for x in o if x["task"] == t]
        per_task[t] = {"entries": len(rows),
                       "fields_present": {f: sum(1 for x in rows if f in x) for f in fields},
                       "test_info_subqueries": sum(len(x.get("test_info", [])) for x in rows),
                       "example": next(x for x in o if x["task"] == t)}
    crr = [x for x in o if x["task"] == "CRR"]
    crr_check = {
        "n": len(crr),
        "entries_where_type0_iff_realtime_lt_clue_time":
            sum(1 for x in crr if all((t["type"] == 0) == (t["realtime"] < x["clue_time"])
                                      for t in x["test_info"])),
        "entries_where_ask_time_lt_clue_time": sum(1 for x in crr if x["ask_time"] < x["clue_time"]),
        "entries_where_ask_time_eq_first_probe":
            sum(1 for x in crr if x["ask_time"] == min(t["realtime"] for t in x["test_info"])),
    }
    return {
        "n_entries": len(o), "n_videos": len({x["video"] for x in o}),
        "n_queries_backward_plus_subqueries":
            sum(1 for x in o if x["task"] in BACK)
            + sum(len(x.get("test_info", [])) for x in o if x["task"] not in BACK),
        "per_task": per_task,
        "meanings": {
            "realtime": "query timestamp. The chunk given to the model is video[0:ceil(realtime)].",
            "realtime_source": "utils/chunk_videos.py:30,39 end_time=math.ceil(data[i]['realtime']); "
                               "clip=video.subclip(0,end_time); consumed at utils/OVOBench.py:30,62",
            "test_info[].realtime": "query timestamp of each successive probe of the same item; "
                                    "chunk is video[0:ceil(realtime)] per probe.",
            "test_info_source": "utils/chunk_videos.py:46,56; utils/OVOBench.py:93-105 "
                                "loops test_info and writes a response per probe",
            "ask_time": "CRR only: the time the question is posed. Strictly earlier than clue_time "
                        "in 48/48 entries and equal to the first probe time in 48/48.",
            "clue_time": "CRR only: the time from which the answer becomes supported by the video. "
                         "test_info[].type is 0 strictly before it and 1 from it onward in 48/48 "
                         "entries, and type selects the ground truth.",
            "clue_time_source": "utils/OVOBenchScore.py:67 gt = 'No' if test_info_['type']==0 else 'Yes'; "
                                "verified against the data (0 violations in 48 entries)",
            "start_times/end_times": "REC only: intervals of each occurrence of the activity.",
            "start_time/end_time": "SSR only: intervals of each tutorial step (parallel to all_steps).",
            "REC_answer_over_time": "test_info[].count is the running number of occurrences visible by "
                                    "that probe time; scored at utils/OVOBenchScore.py:52 "
                                    "get_score_REC(response, test_info_['count'])",
            "SSR_answer_over_time": "test_info[].type flips the yes/no ground truth per step and probe; "
                                    "utils/OVOBenchScore.py:59",
        },
        "crr_clue_time_check": crr_check,
    }


# --------------------------------------------------------------- HERBench
def her():
    out = {}
    for tag, fn in [("full", "herbench_annotations.json"),
                    ("lite_v2", "herbench_annotations_lite_v2.json")]:
        a = json.load(open(DATA / "herbench/hf/data" / fn))
        by_task, forms, lens = {}, collections.Counter(), collections.Counter()
        for x in a:
            rt = (x.get("metadata") or {}).get("required_timestamps")
            t = x["task_type"]
            d = by_task.setdefault(t, {"n": 0, "with_required_timestamps": 0})
            d["n"] += 1
            if rt in (None, "", []):
                forms["absent"] += 1
                continue
            d["with_required_timestamps"] += 1
            if isinstance(rt, str):
                forms["single string 'MM:SS-MM:SS' (one interval)"] += 1
            elif isinstance(rt, list):
                lens[len(rt)] += 1
                if all(" - " in str(e) for e in rt):
                    forms["list of 'HH:MM:SS.mmm - HH:MM:SS.mmm' (intervals)"] += 1
                elif all(" - " not in str(e) for e in rt):
                    forms["list of 'M:SS:mmm' (points)"] += 1
                else:
                    forms["list, mixed"] += 1
        for t, d in by_task.items():
            d["fraction"] = round(d["with_required_timestamps"] / d["n"], 4)
        pop = sum(d["with_required_timestamps"] for d in by_task.values())
        out[tag] = {"n": len(a), "populated": pop, "fraction": round(pop / len(a), 4),
                    "by_task_type": dict(sorted(by_task.items())),
                    "forms": dict(forms.most_common()),
                    "list_length_histogram": dict(sorted(lens.items()))}
    out["meaning"] = {
        "required_timestamps": UNKNOWN,
        "why": "The string 'required_timestamps' does not appear anywhere in the upstream code "
               "repo (grep over DanBenAmi/HERBench @fe66f377), and neither README.md nor "
               "USAGE_GUIDE.md defines it. Its format is read off the data only.",
        "mrfs_does_not_use_it": "MRFS (Minimum Required Frame Set) is computed by searching over "
                                "frame counts chosen by a frame_selector (uniform or BLIP "
                                "similarity) and re-querying the model, not from any annotated "
                                "timestamp.",
        "mrfs_source": "evaluation/calculate_mrfs.py:68-74 (text-only -> MRFS=0; full context "
                       "wrong -> undefined), :218 'mrfs': best_k; "
                       "evaluation/frame_selectors/{uniform,vanila_blip_similarity}.py",
        "event_onset": "REMOVED - no upstream source supports reading these as event onsets.",
    }
    return out


# --------------------------------------------------------------- StreamingBench
def sb():
    B = DATA / "streaming_bench/hf/StreamingBench"
    per_file, gt = {}, {}
    allv = set()
    for p in sorted(glob.glob(f"{B}/*.csv")):
        rows = list(csv.DictReader(open(p)))
        b = os.path.basename(p)
        vids = {re.sub(r"_\d+$", "", r["question_id"]) for r in rows}
        per_file[b] = {"rows": len(rows), "stripped_video_ids": len(vids)}
        if "ground_truth_time_stamp" in rows[0]:
            gt[b] = {"rows_with_gt_time_stamp": sum(1 for r in rows
                                                    if r["ground_truth_time_stamp"].strip()),
                     "videos": len(vids)}
        if b != "Proactive_Output_50.csv":
            allv |= vids
    rows = list(csv.DictReader(open(B / "Proactive_Output.csv")))
    odd = [r["question_id"] for r in rows if not r["question_id"].startswith("Proactive Output_")]
    sample2 = sorted(r["question_id"] for r in rows if r["question_id"].endswith(
        tuple(f"_sample_2_{i}" for i in range(1, 9))))
    return {
        "per_file": per_file, "ground_truth_time_stamp": gt,
        "union_stripped_video_ids_excl_Proactive_Output_50": len(allv),
        "upstream_claim_videos": 900,
        "the_901": {
            "cause": "Within the single video 'sample_2' of Proactive_Output.csv, three rows are "
                     "prefixed 'Proactive Output' and two are prefixed 'Active Output'. Stripping "
                     "the trailing question index therefore yields two ids for one video, so the "
                     "union is 901 rather than 900.",
            "anomalous_question_ids": odd,
            "all_sample_2_question_ids": sample2,
            "note": "Reported only; no data was changed."},
        "meanings": {
            "time_stamp": "query timestamp. The clip handed to the model ends here: "
                          "split_video(video_path, time_start, timestamp) with time_start=0 "
                          "unless a context window is configured.",
            "time_stamp_source": "src/benchmark/StreamingBench.py:41-50; "
                                 "src/utils/video_execution.py:4,23-25 (ffmpeg ss=start, t=end-start)",
            "ground_truth_time_stamp": "Proactive_Output only: the time at which the model is "
                                       "expected to emit ground_truth_output. The harness polls the "
                                       "model once per second from time_stamp+1 until "
                                       "ground_truth_time_stamp+4.",
            "ground_truth_time_stamp_source": "src/benchmark/StreamingBenchProactive.py:35-50 "
                                              "(max_time = ground_truth_time + 4); "
                                              "src/data/count.py:43-57 scores a hit when the output "
                                              "lands within +/-2 s of ground_truth_time",
        },
    }


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    res = {"_note": "Annotation-file structural checks only; no inference, no video decoding.",
           "rtv_bench": rtv(), "ovo_bench": ovo(), "herbench": her(), "streaming_bench": sb()}
    json.dump(res, open(OUT, "w"), indent=1, default=str)
    print("wrote", OUT)
    r = res["rtv_bench"]["recurrence_by_video_and_question_text"]
    print(f"RTV  text-groups>1row={r['groups_gt1_row']} answer-changes={r['groups_where_answer_changes']}")
    print("CRR  check:", res["ovo_bench"]["crr_clue_time_check"])
    print("HER  full fraction:", res["herbench"]["full"]["fraction"])
    print("SB   union ids:", res["streaming_bench"]["union_stripped_video_ids_excl_Proactive_Output_50"])
