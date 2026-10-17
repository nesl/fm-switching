"""StudyV — size-ladder TIMING (no accuracy) on h100nvl, HF, flash_attention_2, batch 1. ORIGINAL .venv.

4B-Instruct, 4B-Thinking, 8B-Instruct on StudyU's 40 ERQA questions, using StudyU's harness unchanged
(study_u_fa2_size.run_trial: per-step timestamps, attn asserted at load and recorded per trial).
8B-Thinking is NOT re-run: StudyU's 40 natural flash-attn trials are reused (phase "natural", attn
flash_attention_2, results/erqa/study_u/study_u_trials_h100nvl.jsonl).
Thinking: CFG-A, max_new_tokens 16384, set_seed(42 + qid). Instruct: greedy, max_new_tokens 512.
"""
import json
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import study_u_fa2_size as U  # noqa: E402

U.REPO.update({
    "4BI": ("Qwen/Qwen3-VL-4B-Instruct", "ebb281ec70b05090aa6165b016eac8ec08e71b17"),
    "4BT": ("Qwen/Qwen3-VL-4B-Thinking", "1de27d8c51f12e819435303b9e84c4e25ba8401e"),
    "8BI": ("Qwen/Qwen3-VL-8B-Instruct", "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"),
})
OUT = Path("results/erqa/study_v")
U.TRIALS_PATH = OUT / "study_v_trials_h100nvl.jsonl"
U.STEPS_PATH = OUT / "study_v_steps_h100nvl.jsonl"
U.CURRENT = Path("logs/study_v_current.json")
THINK = dict(U.GEN)                                   # CFG-A, 16384
INSTRUCT = dict(do_sample=False, max_new_tokens=512)
ATTN = "flash_attention_2"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sel = json.loads(U.SEL_PATH.read_text())
    qids = [q["question_id"] for q in sel["questions"]]
    ds = U.R.load_erqa()
    done = U.done_ids()
    infos = {}
    for key in ("4BI", "4BT", "8BI"):
        U.GEN = THINK if key.endswith("T") else INSTRUCT
        U.MAX_NEW = U.GEN["max_new_tokens"]
        m, p, info = U.load(key, ATTN)
        infos[key] = info
        U.warmup(m, p, ds)
        for qid in qids:
            if f"ladder:{key}:{ATTN}:q{qid}" not in done:
                U.run_trial(m, p, ds, qid, key, ATTN, "ladder", order=1)
        del m, p
        torch.cuda.empty_cache()
    reused = [json.loads(l)["trial_id"] for l in open("results/erqa/study_u/study_u_trials_h100nvl.jsonl")
              if json.loads(l)["phase"] == "natural" and json.loads(l)["attn_implementation"] == ATTN]
    (OUT / "study_v_run_meta_h100nvl.json").write_text(json.dumps(dict(
        models=infos, think_gen=THINK, instruct_gen=INSTRUCT, questions=qids,
        reused_8BT_from_study_u=reused,
        _provenance=U.stamp(script="study_v_size_ladder.py", model="qwen3vl-4bi/4bt/8bi", device=U.DEVICE_SLUG,
                            n=len(U.done_ids()), seed=42)), indent=1))


if __name__ == "__main__":
    main()
