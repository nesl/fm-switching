"""StudyX/StudyW prompt pack — run in the ORIGINAL .venv (transformers 5.10.2), CPU only.

Writes every ERQA question (400) and every StudyT sign (40) as an OpenAI-style message list whose images are the
EXACT images HF's pipeline feeds the model (qwen_vl_utils.process_vision_info output, saved losslessly as PNG), plus
HF's prompt token count. The vLLM client sends these, so both stacks see identical pixels and identical text;
the smoke test checks vLLM's prompt_tokens against `hf_n_input_tokens`.

Output (outside the repo, regenerable): ~/.cache/fm-switching/study_x_prompts/{pack.json, img/*.png}
"""
import hashlib
import json
import sys
from pathlib import Path

from qwen_vl_utils import process_vision_info
from transformers import AutoProcessor

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "erqa"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "signs"))
import study_r_erqa as R  # noqa: E402
import study_t_signs_32b as T  # noqa: E402

OUT = Path.home() / ".cache/fm-switching/study_x_prompts"
PROC_REPO = ("Qwen/Qwen3-VL-32B-Thinking", "7edd10ffd1196091948fb245ff63e406ccb2d4d1")  # same processor family


def to_entry(eid, kind, hf_messages, proc, extra):
    text = proc.apply_chat_template(hf_messages, tokenize=False, add_generation_prompt=True)
    imgs, vids = process_vision_info(hf_messages)
    n_in = int(proc(text=[text], images=imgs, videos=vids, return_tensors="pt")["input_ids"].shape[1])
    content, k = [], 0
    for part in hf_messages[0]["content"]:
        if part["type"] == "image":
            p = OUT / "img" / f"{eid}_{k}.png"
            imgs[k].save(p)
            content.append({"type": "image", "path": str(p), "size": list(imgs[k].size)})
            k += 1
        else:
            content.append({"type": "text", "text": part["text"]})
    return dict(id=eid, kind=kind, content=content, hf_n_input_tokens=n_in,
                hf_chat_text_sha256=hashlib.sha256(text.encode()).hexdigest(), **extra)


def main():
    from huggingface_hub import snapshot_download
    (OUT / "img").mkdir(parents=True, exist_ok=True)
    proc = AutoProcessor.from_pretrained(snapshot_download(PROC_REPO[0], revision=PROC_REPO[1],
                                                           local_files_only=True))
    pack = []
    ds = R.load_erqa()
    for qid in range(len(ds)):
        msgs, correct = R.build_messages(ds[qid])
        pack.append(to_entry(f"erqa{qid}", "erqa", msgs, proc,
                             dict(question_id=qid, correct_letter=correct, category=ds[qid]["question_type"])))
    prompt = T.make_prompt()
    for s in T.load_signs():
        msgs = [{"role": "user", "content": [{"type": "image", "image": s["img"]},
                                             {"type": "text", "text": prompt}]}]
        pack.append(to_entry(f"sign:{s['sign_id']}", "sign", msgs, proc, dict(sign_id=s["sign_id"])))
    (OUT / "pack.json").write_text(json.dumps(pack))
    print(f"wrote {len(pack)} entries to {OUT}")


if __name__ == "__main__":
    main()
