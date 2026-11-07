"""Assemble results/datasets/download_manifest.json from the verification artifacts."""
import json, os, subprocess, collections
from pathlib import Path

D = Path("/mnt/ssd/hf_models/datasets")
REPO = Path("/home/pragya/Desktop/FM-switching")
OUT = REPO / "results/datasets/download_manifest.json"

SPEC = {
    "rtv_bench": dict(
        repo="RTVBench/RTV-Bench", sha="62ec75f8cd7c8ec00ff1c382d950175065bea9b6",
        code_repo="LJungang/RTV-Bench",
        license={"hf_card": "mit", "code_LICENSE": None, "readme": None},
        video_root="hf/videos",
        claims={"videos": 552, "questions_paper": 4631, "questions_readme": 4608}),
    "herbench": dict(
        repo="DanBenAmi/HERBench", sha="30b42e97180f",
        code_repo="DanBenAmi/HERBench",
        license={"hf_card": "cc-by-nc-sa-4.0", "code_LICENSE": "MIT",
                 "readme": "CC BY-NC-SA 4.0 (non-commercial)"},
        video_root="extracted_full",
        claims={"videos_readme": 335, "videos_citation": 337,
                "questions_readme": 27936, "questions_citation": 26806,
                "lite": 5960, "lite_v2": 1971}),
    "ovo_bench": dict(
        repo="JoeLeelyf/OVO-Bench", sha="fec29e338574",
        code_repo="JoeLeelyf/OVO-Bench",
        license={"hf_card": "cc-by-sa-4.0", "code_LICENSE": "MIT",
                 "readme": "CC BY-NC-SA 4.0 -- CONFLICTS WITH HF CARD"},
        video_root="src_videos",
        claims={"videos": 644, "qa_paper": 2814, "queries_readme": 3100}),
    "streaming_bench": dict(
        repo="mjuicem/StreamingBench", sha="48872fa70712",
        code_repo="THUNLP-MT/StreamingBench",
        license={"hf_card": None, "code_LICENSE": "MIT", "readme": None},
        video_root="extracted_by_task",
        claims={"videos": 900, "qa": 4500}),
}


def git_sha(p):
    r = subprocess.run(["git", "-C", str(p), "rev-parse", "HEAD"],
                       capture_output=True, text=True)
    return r.stdout.strip() or None


def du_bytes(p):
    r = subprocess.run(["du", "-sb", str(p)], capture_output=True, text=True)
    try:
        return int(r.stdout.split()[0])
    except Exception:
        return None


def main():
    pre = json.load(open(D / "preflight.json"))
    sizes = json.load(open(D / "size_check.json"))
    cross = json.load(open(REPO / "results/datasets/crosscheck.json"))
    annots = json.load(open(D / "annotations_report.json"))
    archives = {}
    ap = D / "archives.json"
    if ap.exists():
        archives = json.load(open(ap))

    man = {"_note": "StudyDataDownload. Data preparation only; no inference, no GPU. "
                    "Counts are reported against upstream claims and NOT reconciled.",
           "host": "flash (CPU/disk/network only; neither GPU used)",
           "data_root": str(D),
           "data_root_note": "/mnt/ssd is not writable by this user, so /mnt/ssd/datasets "
                             "could not be created; /mnt/ssd/hf_models/datasets was used.",
           "datasets": {}}

    for name, s in SPEC.items():
        hf = pre[s["repo"]]
        vr = D / name / s["video_root"]
        probe = D / name / "ffprobe.jsonl"
        recs = [json.loads(l) for l in probe.open()] if probe.exists() else []
        ok = [r for r in recs if r.get("ok")]
        bad = [r for r in recs if not r.get("ok")]
        durs = sorted(r["duration"] for r in ok if r.get("duration"))
        man["datasets"][name] = {
            "repo_id": s["repo"],
            "commit_sha": hf["sha"],
            "commit_sha_pinned_for_download": s["sha"],
            "code_repo": s["code_repo"],
            "code_repo_sha": git_sha(D / name / "code"),
            "local_path": str(D / name),
            "video_root": str(vr),
            "license": s["license"],
            "hf_declared_license": hf.get("license"),
            "gated": hf.get("gated"),
            "sizes": {
                "hf_files_checked": sizes[name]["present"],
                "hf_size_mismatches": sizes[name]["mismatches"],
                "downloaded_bytes": sizes[name]["bytes"],
                "on_disk_bytes_total": du_bytes(D / name),
            },
            "counts": {
                "videos_on_disk": len(recs),
                "questions": annots[name]["questions"],
                "upstream_claims": s["claims"],
                "crosscheck": {k: v for k, v in cross[name].items()
                               if not isinstance(v, list)},
            },
            "ffprobe": {
                "probed": len(recs), "ok": len(ok), "failures": len(bad),
                "failure_paths": [r["path"] for r in bad][:20],
                "duration_s": {"min": durs[0], "median": durs[len(durs) // 2],
                               "max": durs[-1], "total_hours": round(sum(durs) / 3600, 2)}
                if durs else None,
                "codecs": dict(collections.Counter(r.get("codec") for r in ok)),
            },
            "archives": archives.get(name, "not tested"),
            "verification_status": None,
        }
        d = man["datasets"][name]
        d["verification_status"] = (
            "PASS" if d["sizes"]["hf_size_mismatches"] == 0 and d["ffprobe"]["failures"] == 0
            else "ATTENTION")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(man, open(OUT, "w"), indent=1)
    print("wrote", OUT)
    for k, v in man["datasets"].items():
        print(f"  {k:16s} {v['verification_status']:9s} videos={v['counts']['videos_on_disk']:5d} "
              f"q={v['counts']['questions']:6d} ffprobe_fail={v['ffprobe']['failures']} "
              f"size_mismatch={v['sizes']['hf_size_mismatches']}")


if __name__ == "__main__":
    main()
