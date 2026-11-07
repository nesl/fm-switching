"""Question-to-video cross-check: questions whose video is missing on disk, and
videos on disk that no question references. Annotation + filesystem only."""
import csv, glob, json, os, re, collections
from pathlib import Path

R = Path("/mnt/ssd/hf_models/datasets")
OUT = Path("/home/pragya/Desktop/FM-switching/results/datasets/crosscheck.json")


def rtv():
    q = json.load(open(R / "rtv_bench/hf/QA.json"))
    base = R / "rtv_bench/hf/videos"
    on_disk = {p.name for p in base.rglob("*.mp4")}
    want = collections.Counter(x["video"] for x in q)
    missing = {v: n for v, n in want.items() if v not in on_disk}
    return dict(questions=len(q), videos_referenced=len(want), videos_on_disk=len(on_disk),
                questions_with_missing_video=sum(missing.values()),
                missing_videos=sorted(missing),
                videos_with_no_question=sorted(on_disk - set(want)))


def ovo():
    o = json.load(open(R / "ovo_bench/code/data/ovo_bench_new.json"))
    base = R / "ovo_bench/src_videos"
    # annotations use e.g. "Ego4D/clips/xxx.mp4"; match on the tail path
    on_disk = {}
    for p in base.rglob("*"):
        if p.is_file() and p.suffix in {".mp4", ".mkv", ".webm"}:
            on_disk[p.name] = str(p)
    want = collections.Counter(x["video"] for x in o)
    missing = {v: n for v, n in want.items() if os.path.basename(v) not in on_disk}
    used = {os.path.basename(v) for v in want}
    return dict(entries=len(o), videos_referenced=len(want), videos_on_disk=len(on_disk),
                entries_with_missing_video=sum(missing.values()),
                missing_videos=sorted(missing)[:40], n_missing_videos=len(missing),
                videos_with_no_question=sorted(set(on_disk) - used)[:40],
                n_videos_with_no_question=len(set(on_disk) - used))


def her():
    a = json.load(open(R / "herbench/hf/data/herbench_annotations.json"))
    base = R / "herbench/extracted_full"
    on_disk = {str(p.relative_to(base)) for p in base.rglob("*.mp4")}
    want = collections.Counter(x["video_path"].replace("videos/", "", 1) for x in a)
    missing = {v: n for v, n in want.items() if v not in on_disk}
    return dict(questions=len(a), videos_referenced=len(want), videos_on_disk=len(on_disk),
                questions_with_missing_video=sum(missing.values()),
                missing_videos=sorted(missing),
                videos_with_no_question=sorted(on_disk - set(want)))


def sb():
    base = R / "streaming_bench/extracted_by_task"
    # on-disk key: "<task>/<sample_dir>"
    on_disk = set()
    for p in base.rglob("*.mp4"):
        rel = p.relative_to(base).parts
        on_disk.add(f"{rel[0]}/{rel[1]}")
    want = collections.Counter()
    for f in sorted(glob.glob(str(R / "streaming_bench/hf/StreamingBench/*.csv"))):
        if os.path.basename(f) == "Proactive_Output_50.csv":
            continue
        for r in csv.DictReader(open(f)):
            qid = r["question_id"]
            stripped = re.sub(r"_\d+$", "", qid)        # "<Task>_sample_N"
            m = re.match(r"^(.*)_(sample_\d+)$", stripped)
            if m:
                want[f"{m.group(1)}/{m.group(2)}"] += 1
    missing = {v: n for v, n in want.items() if v not in on_disk}
    return dict(questions=sum(want.values()), video_dirs_referenced=len(want),
                video_dirs_on_disk=len(on_disk),
                questions_with_missing_video=sum(missing.values()),
                missing_videos=sorted(missing),
                videos_with_no_question=sorted(on_disk - set(want)))


if __name__ == "__main__":
    res = {"rtv_bench": rtv(), "ovo_bench": ovo(), "herbench": her(), "streaming_bench": sb()}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(res, open(OUT, "w"), indent=1)
    for k, v in res.items():
        print(f"\n=== {k} ===")
        for kk, vv in v.items():
            if isinstance(vv, list):
                print(f"   {kk}: n={len(vv)} {vv[:6]}")
            else:
                print(f"   {kk}: {vv}")
