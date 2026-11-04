#!/usr/bin/env python3
"""StudyD9 inputs (CPU, HF venv `.venv`; no GPU): reproduce the earlier arms' exact prompts for vLLM.

ERQA (400): study_r_erqa.build_messages (= study_q_erqa); MV-RoboBench (401): study_s2_mvrobobench_32b.build_messages
over results/erqa/study_s2/study_s2_manifest.json. Images are passed through qwen_vl_utils.process_vision_info — the
same pre-resize the HF arms applied before the processor — and stored losslessly as PNG, so vLLM's Qwen3-VL image
processor receives the pixels the HF processor received. For every question the expected prompt length is computed
with the HF processor on CPU (= the earlier arms' n_input_tokens) and the earlier arm C value is recorded alongside.

Output: ~/.cache/fm-switching/d9_inputs/<bench>/<qid>_<k>.png + results/erqa/study_d9/study_d9_inputs_manifest.jsonl
"""
import hashlib
import json
import os
import sys
from pathlib import Path

os.environ["CUDA_VISIBLE_DEVICES"] = ""
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "lib"))
import study_r_erqa as RE  # noqa: E402
import study_s2_mvrobobench_32b as S2  # noqa: E402
from qwen_vl_utils import process_vision_info  # noqa: E402
from transformers import AutoProcessor  # noqa: E402

IMG = Path.home() / ".cache/fm-switching/d9_inputs"
OUT = Path("results/erqa/study_d9")
MAN = OUT / "study_d9_inputs_manifest.jsonl"
PRIOR = {"erqa": Path("results/erqa/study_r/study_r_trials_h100nvl.jsonl"),
         "mvrb": Path("results/erqa/study_s2/study_s2_trials_h100nvl.jsonl")}


def prior_tokens(bench):
    key = "question_id" if bench == "erqa" else "index"
    return {str(r[key]): int(r["n_input_tokens"]) for r in map(json.loads, open(PRIOR[bench])) if r["arm"] == "C"}


def emit(bench, qid, messages, correct, extra, proc, prior, f):
    images, _ = process_vision_info(messages)
    content, k = [], 0
    for c in messages[0]["content"]:
        if c["type"] == "text":
            content.append(dict(type="text", text=c["text"]))
        else:
            p = IMG / bench / f"{qid}_{k}.png"
            p.parent.mkdir(parents=True, exist_ok=True)
            images[k].save(p, format="PNG")
            content.append(dict(type="image", path=str(p), size=list(images[k].size),
                                sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
            k += 1
    assert k == len(images)
    text = proc.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    n = int(proc(text=[text], images=images, return_tensors="pt")["input_ids"].shape[1])
    rec = dict(bench=bench, qid=str(qid), correct_letter=correct, content=content, expected_prompt_tokens=n,
               prior_armC_prompt_tokens=prior.get(str(qid)), **extra)
    f.write(json.dumps(rec) + "\n")
    return rec


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    snap = RE.resolve_snapshot("32BI") if hasattr(RE, "resolve_snapshot") else None
    proc = AutoProcessor.from_pretrained(snap or "Qwen/Qwen3-VL-32B-Instruct")
    mism = {}
    with open(MAN, "w") as f:
        ds = RE.load_erqa()
        pr = prior_tokens("erqa")
        for i in range(len(ds)):
            msgs, correct = RE.build_messages(ds[i])
            r = emit("erqa", i, msgs, correct, dict(category=ds[i]["question_type"], letters="ABCD"), proc, pr, f)
            mism.setdefault("erqa", []).append(r["expected_prompt_tokens"] != r["prior_armC_prompt_tokens"])
        man = json.load(open(S2.MANIFEST))
        root = S2.data_root()
        pr = prior_tokens("mvrb")
        for it in man["items"]:
            msgs = S2.build_messages(it, root)
            r = emit("mvrb", it["index"], msgs, it["correct_letter"],
                     dict(category=it["category"], path=it["path"], letters="ABCDE"), proc, pr, f)
            mism.setdefault("mvrb", []).append(r["expected_prompt_tokens"] != r["prior_armC_prompt_tokens"])
    print({k: f"{sum(v)} of {len(v)} differ from prior arm C n_input_tokens" for k, v in mism.items()})


if __name__ == "__main__":
    main()
