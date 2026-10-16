#!/usr/bin/env python3
"""Study S2: MV-RoboBench spatial strata at 4B and 32B — does thinking pay at 32B?

A FRESH four-arm study (NOT a continuation of StudyS1). StudyS1's manifest, script and trials
exist only on flash and are not on this host; the manifest here is rebuilt from StudyS0 audit1
metadata: ALL questions in spatial_distance_judgement (201) + robotic_trajectory_selection (200).

Arms (all bf16, h100nvl, same prompt):
  I: Qwen3-VL-4B-Instruct   greedy, max_new_tokens=512
  T: Qwen3-VL-4B-Thinking   CFG-A, max_new_tokens=8192
  C: Qwen3-VL-32B-Instruct  greedy, max_new_tokens=512
  D: Qwen3-VL-32B-Thinking  CFG-A, max_new_tokens=8192
CFG-A: temperature=0.6, top_p=0.95, top_k=20, min_p=0, do_sample=True (StudyS0; the model card
  recommends temperature=1.0 — deviation disclosed). Seeding: set_seed(42 + manifest index) per
  question for thinking arms (resume-safe).

Run order: all four arms on spatial_distance_judgement (I, T, C, D), then all four on
robotic_trajectory_selection, so a cost cut drops a category, never an arm.
Projection after 10 new trials of every arm: INFORMATIONAL ONLY. User instruction 2026-10-14:
caps removed; run to completion unless interrupted (no wall cap, no RTS cost cut). --cap-h opts in
to a wall cap. Optional per-arm batching (--batch T=8 ...) for throughput; batched trials record
batch wall time, not single-stream latency (flagged `batched`).

Device: CUDA_VISIBLE_DEVICES=<gpu> so the target GPU is cuda:0 (research/HOST_H100.md).

Usage:
  python experiments/erqa/study_s2_mvrobobench_32b.py --build-manifest
  python experiments/erqa/study_s2_mvrobobench_32b.py                # full run
  python experiments/erqa/study_s2_mvrobobench_32b.py --smoke OUT.jsonl --arms I T --smoke-n 3
"""

import argparse
import gc
import hashlib
import json
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import torch
import transformers
from huggingface_hub import snapshot_download
from PIL import Image
from transformers import set_seed

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import study_r_erqa as R  # noqa: E402  (load_model, prepare, infer_one, REPO)
from _provenance import stamp  # noqa: E402

R.REPO["4BT"] = ("Qwen/Qwen3-VL-4B-Thinking", "1de27d8c51f12e819435303b9e84c4e25ba8401e")

DEVICE_SLUG = "h100nvl"
HF_DATASET = "AaronFengZY24/MV_Robobench"
HF_REVISION = "869ea1113cf2f08498e81f57ced72597238455c0"
S0_META = Path("results/erqa/study_s0/audit1_mvrobobench.json")
OUT_DIR = Path("results/erqa/study_s2")
MANIFEST = OUT_DIR / "study_s2_manifest.json"
JSONL_PATH = OUT_DIR / f"study_s2_trials_{DEVICE_SLUG}.jsonl"
META_PATH = OUT_DIR / f"study_s2_run_meta_{DEVICE_SLUG}.json"

STOP_AT = None  # --stop-at: run-split boundary in fixed manifest order (user instruction 2026-10-14)
CATS = ["spatial_distance_judgement", "robotic_trajectory_selection"]
MAX_NEW_THINKING = 8192
MAX_NEW_INSTRUCT = 512
THINKING_GEN = dict(do_sample=True, temperature=0.6, top_p=0.95, top_k=20, min_p=0.0,
                    max_new_tokens=MAX_NEW_THINKING)
INSTRUCT_GEN = dict(do_sample=False, max_new_tokens=MAX_NEW_INSTRUCT)
ARMS = {"I": ("4BI", False), "T": ("4BT", True), "C": ("32BI", False), "D": ("32BT", True)}
ARM_ORDER = ["I", "T", "C", "D"]
PROJECT_AFTER = 10
CAP_H = None  # user instruction 2026-10-14: no wall cap, no cost cut; --cap-h opts in
PROJECTION_REF_H = 7.0  # projections are compared to the former cap, informational only
PRIOR_S = {"I": 1.0, "T": 60.0, "C": 2.0, "D": 150.0}  # informational only
DECODE_32B_TOK_S = 22.6  # StudyR bf16 probe, 32B-Thinking on H100 NVL

PROMPT_SUFFIX = "Answer with the option's letter from the given choices directly."


# --------------------------------------------------------------------------- manifest

def build_manifest():
    d = json.load(open(S0_META))
    items = []
    for c in CATS:
        for r in sorted((r for r in d["records"] if r["category"] == c), key=lambda r: r["path"]):
            qa = r["qa"]
            assert [i["path"].lstrip("./") for i in qa["images"]] == r["image_names"], r["path"]
            items.append(dict(index=len(items), path=r["path"], category=c, source=r["source"],
                              n_views=r["n_views"], image_names=r["image_names"],
                              illustrations=[i.get("illustration") for i in qa["images"]],
                              question=qa["question"], options=qa["options"],
                              correct_letter=qa["correct"], type=qa["type"]))
    assert len(items) == 401 and len({i["path"] for i in items}) == 401
    out = dict(
        study="StudyS2", n=len(items),
        n_by_category={c: sum(i["category"] == c for i in items) for c in CATS},
        provenance_note=("Rebuilt from StudyS0 audit1 metadata, NOT copied from StudyS1: S1's manifest, "
                         "script and trials exist only on flash and are not on this host or in the repo. "
                         "Selection rule: ALL questions in spatial_distance_judgement and "
                         "robotic_trajectory_selection (no sampling). Order: SDJ then RTS, each sorted by "
                         "path; `index` is the seed offset for thinking arms."),
        source_file=str(S0_META), source_sha256=hashlib.sha256(S0_META.read_bytes()).hexdigest(),
        hf_dataset=HF_DATASET, hf_revision=HF_REVISION, items=items)
    out["_provenance"] = stamp(script="study_s2_mvrobobench_32b.py", model="none", device="cpu",
                               n=len(items))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(out, indent=1))
    print(f"wrote {MANIFEST}: {out['n_by_category']}")


def data_root():
    return Path(snapshot_download(HF_DATASET, repo_type="dataset", revision=HF_REVISION,
                                  allow_patterns=["*/QA.json"], local_files_only=True))


# --------------------------------------------------------------------------- prompt / parse

def build_messages(item, root):
    """Views in order, each labelled with its index and illustration, then question + options."""
    content = []
    for k, (name, ill) in enumerate(zip(item["image_names"], item["illustrations"]), 1):
        label = f"View {k}" + (f" ({ill})" if ill else "") + ":"
        content.append({"type": "text", "text": label})
        content.append({"type": "image", "image": Image.open(root / item["path"] / name).convert("RGB")})
    opts = "\n".join(f"{k}. {v}" for k, v in sorted(item["options"].items()))
    text = f"{item['question']}\nOptions:\n{opts}\n{PROMPT_SUFFIX}"
    content.append({"type": "text", "text": text})
    return [{"role": "user", "content": content}]


def prompt_string(item):
    """Text-only rendering of the prompt (images as <image>) for the trial record."""
    parts = []
    for k, ill in enumerate(item["illustrations"], 1):
        parts.append(f"View {k}" + (f" ({ill})" if ill else "") + ": <image>")
    opts = "\n".join(f"{k}. {v}" for k, v in sorted(item["options"].items()))
    parts.append(f"{item['question']}\nOptions:\n{opts}\n{PROMPT_SUFFIX}")
    return "\n".join(parts)


def extract_letter(text, letters="ABCDE"):
    """study_r_erqa.extract_letter widened to A–E."""
    t = text.strip()
    if t and t[0] in letters and (len(t) == 1 or t[1] in '.\n ):,'):
        return t[0], "direct"
    m = re.search(rf'(?:answer is|answer:|the answer)\s*[:\s]*([{letters}])\b', t, re.IGNORECASE)
    if m:
        return m.group(1).upper(), "extracted"
    m = re.search(rf'\b([{letters}])\b', t[-80:])
    if m:
        return m.group(1).upper(), "last_found"
    return None, "no_letter"


# --------------------------------------------------------------------------- run

def infer_batch(model, proc, batch_msgs, gen_kwargs, is_thinking, seed):
    """Batched generate (left padding). Per-trial outputs mirror R.infer_one; latency_ms is the batch
    wall time (NOT single-stream latency) and is flagged via `batched`."""
    from qwen_vl_utils import process_vision_info
    texts = [proc.apply_chat_template(m, tokenize=False, add_generation_prompt=True) for m in batch_msgs]
    imgs, vids = process_vision_info(batch_msgs)
    proc.tokenizer.padding_side = "left"
    inputs = proc(text=texts, images=imgs, videos=vids, padding=True, return_tensors="pt").to("cuda:0")
    n_in_padded = inputs["input_ids"].shape[1]
    n_inputs = inputs["attention_mask"].sum(dim=1).tolist()
    set_seed(seed)
    torch.cuda.reset_peak_memory_stats(0)
    torch.cuda.synchronize()
    t0 = time.time()
    with torch.no_grad():
        out = model.generate(**inputs, **gen_kwargs)
    torch.cuda.synchronize()
    lat_ms = (time.time() - t0) * 1000
    peak_gb = torch.cuda.max_memory_allocated(0) / 1e9
    reserved_gb = torch.cuda.max_memory_reserved(0) / 1e9
    pad_id = proc.tokenizer.pad_token_id
    eos_ids = gen_kwargs.get("eos_token_id") or model.generation_config.eos_token_id
    eos_ids = set(eos_ids if isinstance(eos_ids, (list, tuple)) else [eos_ids])
    res = []
    for b in range(len(batch_msgs)):
        gen = out[b][n_in_padded:].tolist()
        n_gen = len(gen)
        for k, tok in enumerate(gen):
            if tok in eos_ids:
                n_gen = k + 1
                break
        while n_gen and gen[n_gen - 1] == pad_id and pad_id not in eos_ids:
            n_gen -= 1
        full = proc.decode(gen[:n_gen], skip_special_tokens=True)
        budget_hit = n_gen >= gen_kwargs["max_new_tokens"]
        n_think, think_closed = 0, None
        if is_thinking:
            think_closed = "</think>" in full
            if think_closed:
                think_part, answer_part = full.split("</think>", 1)
                answer_text = answer_part.strip()
                n_think = len(proc.tokenizer.encode(re.sub(r'^<think>', '', think_part).strip(),
                                                    add_special_tokens=False))
            else:
                answer_text = full
        else:
            answer_text = full.strip()
        n_answer = len(proc.tokenizer.encode(answer_text, add_special_tokens=False)) if answer_text else 0
        res.append(dict(answer_text=answer_text, raw_output=full, n_input_tokens=int(n_inputs[b]),
                        n_think_tokens=n_think, n_answer_tokens=n_answer, n_generated=n_gen,
                        total_latency_ms=round(lat_ms, 1), budget_hit=budget_hit, think_closed=think_closed,
                        peak_alloc_gb=round(peak_gb, 2), peak_reserved_gb=round(reserved_gb, 2)))
    return res


def load_done(path):
    done = defaultdict(set)
    if path.exists():
        for line in open(path):
            if line.strip():
                t = json.loads(line)
                done[t["arm"]].add(t["path"])
    return done


def save_meta(meta):
    META_PATH.write_text(json.dumps(meta, indent=2, default=str))


def run_block(arm, cat, items, root, out_f, done, meta, state, smoke_gen=None):
    """Run one arm on one category. Returns False if the wall cap was hit."""
    key, is_thinking = ARMS[arm]
    todo = [it for it in items if it["category"] == cat and it["path"] not in done[arm]
            and (STOP_AT is None or it["index"] < STOP_AT)]
    if not todo:
        print(f"[{arm}/{cat[:3]}] nothing to do", flush=True)
        return True
    if state.get("loaded") != key:
        state.pop("model", None), state.pop("proc", None)
        gc.collect()
        torch.cuda.empty_cache()
        model, proc, info = R.load_model(key, "bf16")
        state.update(model=model, proc=proc, loaded=key)
        meta.setdefault("arms", {}).setdefault(arm, {}).update(info)
    model, proc = state["model"], state["proc"]
    gen = smoke_gen or (THINKING_GEN if is_thinking else INSTRUCT_GEN)
    snap = f"{R.REPO[key][0]}@{R.REPO[key][1]}"
    am = meta["arms"][arm]
    bs = state.get("batch", {}).get(arm, 1)
    am["batch_size"] = bs
    projected = len(state["lat"][arm]) >= PROJECT_AFTER
    for j in range(0, len(todo), bs):
        chunk = todo[j:j + bs]
        if CAP_H and time.time() - state["t0"] > CAP_H * 3600:
            meta["wall_cap_hit"] = dict(at=datetime.now().isoformat(), arm=arm, category=cat)
            save_meta(meta)
            print(f"=== WALL CAP {CAP_H}h HIT during {arm}/{cat}; stopping ===", flush=True)
            return False
        t_start = datetime.now().isoformat()
        if bs == 1:
            seed = 42 + chunk[0]["index"] if is_thinking else None
            rs = [R.infer_one(model, proc, build_messages(chunk[0], root), gen, is_thinking, seed=seed)]
            seeds = [seed]
        else:
            seed = 42 + chunk[0]["index"]  # one seed per batch (greedy arms ignore it)
            rs = infer_batch(model, proc, [build_messages(it, root) for it in chunk], gen, is_thinking, seed)
            seeds = [seed if is_thinking else None] * len(chunk)
        t_end = datetime.now().isoformat()
        for it, r, sd in zip(chunk, rs, seeds):
            pred, status = extract_letter(r["answer_text"])
            r.update(arm=arm, path=it["path"], index=it["index"], category=cat, source=it["source"],
                     n_views=it["n_views"], model_snapshot=snap, quant="bf16", prompt=prompt_string(it),
                     pred=pred, parse_status=status, correct_letter=it["correct_letter"],
                     correct=(pred == it["correct_letter"]) if pred else False, seed=sd,
                     batch_size=bs, batch_first_index=chunk[0]["index"], batched=bs > 1,
                     latency_ms=r["total_latency_ms"], wall_start=t_start, wall_end=t_end,
                     max_new_tokens=gen["max_new_tokens"], _hardware=DEVICE_SLUG,
                     attn_implementation=model.config._attn_implementation)
            out_f.write(json.dumps(r) + "\n")
            done[arm].add(it["path"])
            am["peak_alloc_gb"] = max(am.get("peak_alloc_gb", 0), r["peak_alloc_gb"])
            am["peak_reserved_gb"] = max(am.get("peak_reserved_gb", 0), r["peak_reserved_gb"])
            state["lat"][arm].append(r["latency_ms"] / 1000 / len(chunk))  # effective s per trial
            state["tok"][arm].append(r["n_generated"])
        out_f.flush()
        n_new = len(state["lat"][arm])
        if n_new // 10 != (n_new - len(chunk)) // 10:
            r = rs[-1]
            print(f"[{arm}/{cat[:3]}] {len(done[arm])} done (+{n_new} this run, bs={bs}) last {chunk[-1]['path']} "
                  f"gen={r['n_generated']} call={r['latency_ms']/1000:.1f}s "
                  f"eff={state['lat'][arm][-1]:.1f}s/trial peak={am['peak_reserved_gb']:.1f}GB", flush=True)
        if not projected and n_new >= PROJECT_AFTER and not smoke_gen:
            projected = True
            project(arm, items, done, meta, state)
    save_meta(meta)
    return True


def project(arm, items, done, meta, state):
    """Project total S2 time over all arms. Unmeasured arms use priors (D from T's mean generated
    tokens at the StudyR-probe 32B decode rate). The projection is BINDING (may drop RTS) only once
    all four arms have >= PROJECT_AFTER new trials, i.e. at arm D's projection, which falls before
    any RTS trial runs; earlier projections are informational."""
    mean = {a: sum(v) / len(v) for a, v in state["lat"].items() if len(v) >= PROJECT_AFTER}
    est, src = {}, {}
    for a in ARM_ORDER:
        if a in mean:
            est[a], src[a] = mean[a], "measured"
        elif a == "D" and state["tok"]["T"]:
            est[a] = sum(state["tok"]["T"]) / len(state["tok"]["T"]) / DECODE_32B_TOK_S
            src[a] = f"T mean tokens / {DECODE_32B_TOK_S} tok/s"
        else:
            est[a], src[a] = PRIOR_S[a], "prior"
    elapsed_h = (time.time() - state["t0"]) / 3600
    rem = {c: sum(est[a] * sum(1 for it in items if it["category"] == c and it["path"] not in done[a])
                  for a in ARM_ORDER) / 3600 for c in CATS}
    total_h = elapsed_h + rem[CATS[0]] + rem[CATS[1]]
    binding = all(a in mean for a in ARM_ORDER)
    decision = ("within" if total_h <= PROJECTION_REF_H else "exceeds") + f" {PROJECTION_REF_H}h reference (informational; no action)"
    p = dict(after_arm=arm, at=datetime.now().isoformat(), binding=binding,
             est_s_per_trial={k: round(v, 2) for k, v in est.items()}, est_source=src,
             elapsed_h=round(elapsed_h, 2),
             remaining_h_by_category={c: round(v, 2) for c, v in rem.items()},
             projected_total_h=round(total_h, 2), reference_h=PROJECTION_REF_H, note=decision)
    meta.setdefault("projections", []).append(p)
    save_meta(meta)
    print(f"=== PROJECTION {arm} (informational{', all arms measured' if binding else ', priors for unmeasured arms'}): est s/trial "
          f"{({k: round(v, 1) for k, v in est.items()})} elapsed {elapsed_h:.2f}h, remaining "
          f"SDJ {rem[CATS[0]]:.2f}h + RTS {rem[CATS[1]]:.2f}h -> total {total_h:.2f}h; {decision} ===", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-manifest", action="store_true")
    ap.add_argument("--arms", nargs="+", default=ARM_ORDER, help="arms in run order within each category")
    ap.add_argument("--smoke", help="write N trials per arm to this JSONL with small budgets; no projection")
    ap.add_argument("--smoke-n", type=int, default=3)
    ap.add_argument("--smoke-budget", type=int, default=1024)
    ap.add_argument("--attn", choices=["flash_attention_2", "sdpa"], default="flash_attention_2",
                    help="flash_attention_2 is mandatory and asserted at load (R.load_model); "
                         "flash-attn runs write *_fa2 files")
    ap.add_argument("--stop-at", type=int, default=None,
                    help="only run manifest indices < N (fixed manifest order); a later launch without it resumes the same run")
    ap.add_argument("--cap-h", type=float, default=None, help="opt-in wall cap in hours (default: none)")
    ap.add_argument("--batch", nargs="*", default=[], help="per-arm batch size, e.g. T=16 D=8 (default 1)")
    ap.add_argument("--smoke-cats", nargs="+", default=CATS)
    args = ap.parse_args()
    global JSONL_PATH, META_PATH
    R.set_attn(args.attn)
    if args.attn == "flash_attention_2":
        JSONL_PATH = OUT_DIR / f"study_s2_trials_{DEVICE_SLUG}_fa2.jsonl"
        META_PATH = OUT_DIR / f"study_s2_run_meta_{DEVICE_SLUG}_fa2.json"
    if args.build_manifest:
        build_manifest()
        return

    print(f"cuda:0 = {torch.cuda.get_device_name(0)}; transformers {transformers.__version__}; "
          f"torch {torch.__version__}", flush=True)
    if transformers.__version__.startswith("5.17"):
        print("!!! WARNING: transformers 5.17.x — Qwen3-VL repetition-loop regression (olmo-eval #441) !!!",
              flush=True)
    man = json.loads(MANIFEST.read_text())
    items = man["items"]
    root = data_root()
    state = {"t0": time.time(), "lat": defaultdict(list), "tok": defaultdict(list),
             "batch": {kv.split("=")[0]: int(kv.split("=")[1]) for kv in args.batch}}

    if args.smoke:
        out = Path(args.smoke)
        meta = {"smoke": True}
        sm_items = [it for c in args.smoke_cats for it in [x for x in items if x["category"] == c][::20][:args.smoke_n]]

        with open(out, "a") as f:
            for arm in args.arms:
                gen = dict(THINKING_GEN if ARMS[arm][1] else INSTRUCT_GEN)
                gen["max_new_tokens"] = min(gen["max_new_tokens"], args.smoke_budget)
                for cat in args.smoke_cats:
                    run_block(arm, cat, sm_items, root, f, defaultdict(set), meta, state, smoke_gen=gen)
        print(json.dumps(meta.get("arms", {}), indent=1, default=str))
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = json.loads(META_PATH.read_text()) if META_PATH.exists() else {}
    global CAP_H, STOP_AT
    CAP_H = args.cap_h
    STOP_AT = args.stop_at
    meta.setdefault("runs", []).append(dict(start=datetime.now().isoformat(), cap_h=CAP_H,
                                            arms=args.arms, stop_at=args.stop_at))
    # an opt-in cap runs from the FIRST launch, so a crash-resume does not reset it
    state["t0"] = datetime.fromisoformat(meta["runs"][0]["start"]).timestamp()
    meta.update(attn_implementation=R.ATTN, transformers=transformers.__version__, torch=torch.__version__,
                gpu=torch.cuda.get_device_name(0), quant="bf16 (all arms)", manifest=str(MANIFEST),
                n=len(items), n_by_category=man["n_by_category"], hf_dataset=HF_DATASET,
                hf_revision=HF_REVISION, thinking_gen=THINKING_GEN, instruct_gen=INSTRUCT_GEN,
                prompt_suffix=PROMPT_SUFFIX, batch=state["batch"], models={a: R.REPO[ARMS[a][0]] for a in ARM_ORDER})
    save_meta(meta)
    done = load_done(JSONL_PATH)
    arms = [a for a in args.arms if a in ARMS]  # run order as given (default I T C D)
    meta["arm_order"] = arms
    ok = True
    with open(JSONL_PATH, "a") as out_f:
        for cat in CATS:
            for arm in arms:
                ok = run_block(arm, cat, items, root, out_f, done, meta, state)
                if not ok:
                    break
            if not ok:
                break
    meta["n_done"] = {a: len(done[a]) for a in arms}
    meta["completed"] = ok and all(len(done[a]) == 401 for a in arms)
    meta["_provenance"] = stamp(script="study_s2_mvrobobench_32b.py", model="qwen3vl_4b_32b",
                                device=DEVICE_SLUG, n=len(items), seed=42, args=args)
    save_meta(meta)
    print(f"STUDY S2 run finished: {meta['n_done']}. GIT RULE: do not commit; ask the user.", flush=True)


if __name__ == "__main__":
    main()
