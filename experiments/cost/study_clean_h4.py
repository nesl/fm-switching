#!/usr/bin/env python3
"""StudyClean H4 (ORIGINAL .venv: transformers 5.10.2, torch 2.8.0+cu128; h100nvl GPU 1 via CUDA_VISIBLE_DEVICES).

Qwen3-VL-4B-Instruct on the 401 MV-RoboBench questions with StudyS2's own script, prompt and manifest: arm I
(greedy, max_new_tokens 512, batch 1), SDPA (asserted at load by study_r_erqa.load_model). Only the output paths
change (results/cost/study_clean/). Reference: StudyS2 arm C sdpa (study_s2_trials_h100nvl.jsonl, GPU 3).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "erqa"))
import study_s2_mvrobobench_32b as S2  # noqa: E402

OUT = Path("results/cost/study_clean")
S2.OUT_DIR = OUT
S2.JSONL_PATH = OUT / "study_clean_h4_trials_h100nvl.jsonl"
S2.META_PATH = OUT / "study_clean_h4_run_meta_h100nvl.json"

if __name__ == "__main__":
    assert S2.MANIFEST == Path("results/erqa/study_s2/study_s2_manifest.json")
    sys.argv = [sys.argv[0], "--arms", "I", "--attn", "sdpa"]
    S2.main()
