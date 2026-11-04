#!/usr/bin/env python3
"""StudyD11 pre-sweep check (CPU, no model): can arm U (sorted union of K3 RECENT and K1 RICH frames) be sent in K1/K3's
format without misrepresenting timing or overflowing --max-model-len 32768?

K1/K3 format (study_r1_vllm.body): ONE video per request, frames at the question's final_hw, VideoMetadata fps 1.0 with
frames_indices = round(t); Qwen3-VL fuses consecutive frame PAIRS into one temporal patch (temporal_patch_size 2) and
labels each pair with the mean of its two timestamps (vLLM qwen3_vl._calculate_timestamps).
Reports, per option: frame size used, token estimate ((n_frames+1)//2 * (h/32)*(w/32) + text), how many questions exceed
32,768, and for the single-video union how many temporal pairs join frames whose spacing differs from the pair before.
Writes results/cost/study_d11/study_d11_format_check.json.
"""
import collections
import json
from pathlib import Path
import gzip

M = Path("results/sember/study_r1/study_r1_inputs_manifest.jsonl.gz")
OUT = Path("results/cost/study_d11/study_d11_format_check.json")


def vis(n, hw):
    return ((n + 1) // 2) * (hw[0] // 32) * (hw[1] // 32)


def main():
    rows = collections.defaultdict(dict)
    for r in map(json.loads, gzip.open(M)):
        rows[r["question_id"]][r["construction"]] = r
    res = dict(n=len(rows), sizes=collections.Counter(), options={})
    A, B, C = [], [], []
    pair_stats = dict(questions_qt_gt_120=0, questions_nonuniform=0, pairs_total=0, pairs_gap_gt_1s=0,
                      pairs_mixing_rich_and_recent=0)
    same_hw = 0
    for q, c in rows.items():
        k3, k1 = c["RECENT"], c["RICH"]
        res["sizes"][f"K3 {tuple(k3['final_hw'])} / K1 {tuple(k1['final_hw'])}"] += 1
        same_hw += k3["final_hw"] == k1["final_hw"]
        u = sorted(set(k3["frame_t"]) | set(k1["frame_t"]))
        text_k3 = k3["n_input_instruct"] - vis(k3["n_frames"], k3["final_hw"])
        A.append(vis(len(u), k1["final_hw"]) + text_k3)
        B.append(vis(len(u), k3["final_hw"]) + text_k3)
        C.append(vis(k1["n_frames"], k1["final_hw"]) + vis(k3["n_frames"], k3["final_hw"]) + text_k3 + 20)
        if k3["question_time"] > 120:
            pair_stats["questions_qt_gt_120"] += 1
            gaps = [round(u[i + 1] - u[i], 3) for i in range(len(u) - 1)]
            pair_stats["questions_nonuniform"] += len(set(gaps)) > 1
            rec = set(k3["frame_t"])
            for i in range(0, len(u) - 1, 2):
                pair_stats["pairs_total"] += 1
                pair_stats["pairs_gap_gt_1s"] += (u[i + 1] - u[i]) > 1.0 + 1e-6
                pair_stats["pairs_mixing_rich_and_recent"] += (u[i] in rec) != (u[i + 1] in rec)
    def summ(x):
        x = sorted(x)
        return dict(max=x[-1], p50=x[len(x) // 2], over_32768=sum(v > 32768 for v in x))
    res["sizes"] = dict(res["sizes"].most_common())
    res["questions_k1_k3_same_size"] = same_hw
    res["options"] = {
        "A_single_union_video_at_K1_size": dict(tokens=summ(A), timing="text timestamps exact per pair midpoint; "
                                                "pairs fuse frames of unequal spacing", recent_frames_downscaled=len(rows) - same_hw),
        "B_single_union_video_at_K3_size": dict(tokens=summ(B)),
        "C_two_videos_K1_then_K3_exact": dict(tokens=summ(C), note="each video uniform and byte-identical to K1/K3; "
                                              "frames inside the last 120 s appear in both; needs video limit 2"),
        "D_separate_images_with_time_markers": dict(note="exact timing at any size, but image format differs from K1/K3 "
                                                    "(video); tokens not estimated")}
    res["single_video_pairing"] = pair_stats
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1)[:2500])


if __name__ == "__main__":
    main()
