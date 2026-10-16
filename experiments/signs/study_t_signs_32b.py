"""
StudyT — SiGNgapore2D non-termination at 32B (h100nvl).

Does scale buy TERMINATION? Prior: 4B-Thinking 70% (28/40) and 8B-Thinking 90% (36/40) terminate
at max_new_tokens=8192 on the StudyJ2 40-sign manifest (StudyP); 4B never-terminate asymptote 20%
(8/40) at budgets up to 24,576 (StudyJ2).

Pre-registration: reports/study_t_signs_32b.md (written before any 32B sign trial).

Mirrors StudyP/StudyJ2 exactly for: manifest (results/signs/study_j2/manifest.json), crop
(crop_bbox), prompt (prompt.txt with first 10 symbols + DIRECTIONS), message order
[image, text], seeding (torch.manual_seed(42) immediately before each trial), decoding
(skip_special_tokens=False, split on </think>), parsing (parse_prediction).
Scoring is NOT done here — see study_t_score.py (offline; generation never depends on open_clip).

Arms (bf16, device_map={"":0}; run with CUDA_VISIBLE_DEVICES=<gpu>):
  I32 = Qwen3-VL-32B-Instruct @0cfaf481, greedy, max_new_tokens=8192 (= StudyP arm D's INSTRUCT_GEN)
  T32 = Qwen3-VL-32B-Thinking @7edd10ff, CFG-A (temp 0.6, top_p 0.95, top_k 20, min_p 0, do_sample),
        max_new_tokens=8192, seed 42
Order: I32 first (bounded, ~minutes), then T32 — so the bounded baseline completes even if the
T32 core hits the 2 h cap.

Phases:
  core    — I32@8192 + T32@8192, all 40 signs. CAP 2 h wall-clock (no new trial starts after it).
  ladder  — LEFTOVER-TIME EXTENSION (user decision 4, 2026-10-14), not part of the capped core:
            every T32 sign with think_closed=False at 8192 is re-run at 16384 (same seed 42), and
            every sign still not closed at 16384 is re-run at 24576 — StudyJ2's budget ladder.
            Each rung re-generates from scratch; with identical inputs and seed the first B tokens
            should reproduce the previous rung — this is CHECKED per sign (prefix_match field),
            not assumed.

Output (append-per-trial, resume-safe on (arm, budget, sign_id)):
  results/signs/study_t/study_t_trials_h100nvl.jsonl
  results/signs/study_t/study_t_run_meta_h100nvl.json
"""
import argparse
import ast
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

PROMPT_PATH  = "/tmp/sign-understanding/prompts/prompt.txt"
SYMBOLS_PATH = "/tmp/sign-understanding/prompts/symbols.txt"
GT_PATH      = "/tmp/sign-understanding/gt/gt_annotation.json"
J2_MANIFEST  = "results/signs/study_j2/manifest.json"
HF_REPO      = "NickyZimmerman/SiGNgapore2D"
HF_REPO_SHA  = "97d148794fc933e5cf40bf85d8c711437de6b48e"   # pinned 2026-10-14 (J2/P did not pin)

REPO = {
    "I32": ("Qwen/Qwen3-VL-32B-Instruct", "0cfaf48183f594c314753d30a4c4974bc75f3ccb"),
    "T32": ("Qwen/Qwen3-VL-32B-Thinking", "7edd10ffd1196091948fb245ff63e406ccb2d4d1"),
}
DEVICE_SLUG = "h100nvl"
OUT_DIR     = Path("results/signs/study_t")
TRIALS_PATH = OUT_DIR / f"study_t_trials_{DEVICE_SLUG}.jsonl"
META_PATH   = OUT_DIR / f"study_t_run_meta_{DEVICE_SLUG}.json"
SDPA_TRIALS_PATH = TRIALS_PATH  # the 2026-10-14 SDPA run (source of the long-trace list for --phase longdiag)
LONGDIAG_PATH = OUT_DIR / f"study_t_longtrace_{DEVICE_SLUG}_fa2.jsonl"
# Attention backend (2026-10-15 flash-attn re-run): flash_attention_2 is MANDATORY and asserted after every
# load (Qwen3-VL silently falls back to sdpa when flash-attn is not importable). flash-attn runs write *_fa2
# files and run with no core cap (user instruction 2026-10-15: no time restriction).
ATTN = "flash_attention_2"

SEED        = 42
CORE_BUDGET = 8192
LADDER      = [16384, 24576]
CORE_CAP_H  = 2.0   # user instruction 2026-10-14 (interleaved plan): StudyT core 2 h cap reinstated
DIRECTIONS  = ['left', 'right', 'straight', 'straight-right', 'straight-left', 'locational']
THINKING_GEN = dict(do_sample=True, temperature=0.6, top_p=0.95, top_k=20, min_p=0.0)
INSTRUCT_GEN = dict(do_sample=False)


# ── Verbatim from study_p_retry_vs_scale.py (make_prompt, crop_bbox, parse_prediction) ──

def make_prompt():
    raw     = open(PROMPT_PATH).read()
    symbols = [l.strip() for l in open(SYMBOLS_PATH) if l.strip()]
    sym_str = ", ".join(symbols[:10])
    return (raw
            .replace("GT_SYMBOL_LIST", sym_str)
            .replace("REPLACE_DIRECTION_LIST", str(DIRECTIONS)))


def crop_bbox(img, bbox):
    cx, cy, w, h = bbox
    return img.crop((max(0, int(cx-w/2)), max(0, int(cy-h/2)),
                     min(img.width, int(cx+w/2)), min(img.height, int(cy+h/2))))


def parse_prediction(answer_text):
    text = re.sub(r"```(?:json)?", "", answer_text).strip().strip("`").strip()
    text = text.replace("<|im_end|>", "").strip()
    for parser in (ast.literal_eval, json.loads):
        try:
            d = parser(text)
            if isinstance(d, dict):
                T = d.get("T", d.get("t", {})) or {}
                S = d.get("S", d.get("s", {})) or {}
                return {"T": T, "S": S}, "ok"
        except Exception:
            pass
    return None, "parse_failed"


def split_think(full_output, tokenizer):
    """study_p extract_think_and_answer, plus raw think content length."""
    if "</think>" in full_output:
        tp, ap = full_output.split("</think>", 1)
        think_content = tp.replace("<think>", "").strip()
        answer_text   = ap.strip()
        think_closed  = True
    else:
        think_content = full_output.replace("<think>", "").strip()
        answer_text   = ""
        think_closed  = False
    n_think = len(tokenizer.encode(think_content, add_special_tokens=False)) if think_content else 0
    return answer_text, n_think, think_closed


def bin_of(n_gt):
    if 1 <= n_gt <= 2:
        return "low"
    if 3 <= n_gt <= 5:
        return "mid"
    if n_gt >= 6:
        return "high"
    return "other"


# ── IO ─────────────────────────────────────────────────────────────────────────

def load_trials():
    rows = []
    if TRIALS_PATH.exists():
        for line in open(TRIALS_PATH):
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_meta():
    return json.load(open(META_PATH)) if META_PATH.exists() else {}


def save_meta(meta):
    META_PATH.write_text(json.dumps(meta, indent=2, default=str))


def load_signs():
    from huggingface_hub import hf_hub_download
    from PIL import Image
    manifest = json.load(open(J2_MANIFEST))
    imgs = {}
    signs = []
    for e in manifest:
        if e['imagePath'] not in imgs:
            local = hf_hub_download(repo_id=HF_REPO, filename=f"images/{e['imagePath']}",
                                    repo_type="dataset", revision=HF_REPO_SHA)
            imgs[e['imagePath']] = Image.open(local).convert("RGB")
        signs.append(dict(sign_id=e['crop'], crop_name=e['crop'], imagePath=e['imagePath'],
                          n_gt=e['n_gt'], bin=bin_of(e['n_gt']),
                          img=crop_bbox(imgs[e['imagePath']], e['bbox'])))
    return signs


# ── Model ──────────────────────────────────────────────────────────────────────

def load_model(arm):
    import torch
    from huggingface_hub import snapshot_download
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
    repo, rev = REPO[arm]
    path = snapshot_download(repo, revision=rev, local_files_only=True)
    torch.cuda.reset_peak_memory_stats(0)
    t0 = time.time()
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        path, dtype=torch.bfloat16, device_map={"": 0}, attn_implementation=ATTN).eval()
    got = getattr(model.config, "_attn_implementation", None)
    if got != ATTN:
        raise SystemExit(f"!!! ATTENTION BACKEND ASSERT FAILED: requested {ATTN}, model uses {got} — aborting !!!")
    processor = AutoProcessor.from_pretrained(path)
    info = dict(arm=arm, repo=repo, revision=rev, snapshot_path=path, quant="bf16",
                attn_implementation=getattr(model.config, "_attn_implementation", None),
                load_s=round(time.time() - t0, 1),
                weights_allocated_gb=round(torch.cuda.memory_allocated(0) / 1e9, 2))
    print(f"Loaded {arm}: {info}", flush=True)
    return model, processor, info


def run_one(model, processor, sign, prompt, arm, budget, min_new_tokens=None):
    import torch
    from qwen_vl_utils import process_vision_info
    is_thinking = arm == "T32"
    gen_kwargs = dict(THINKING_GEN if is_thinking else INSTRUCT_GEN, max_new_tokens=budget)
    if min_new_tokens:
        gen_kwargs["min_new_tokens"] = min_new_tokens  # forced-length VRAM probe only
    torch.manual_seed(SEED)   # mirrors StudyJ2/StudyP: reseed immediately before each trial
    messages = [{"role": "user", "content": [
        {"type": "image", "image": sign['img']},
        {"type": "text",  "text": prompt}]}]
    text_input = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    img_inp, vid_inp = process_vision_info(messages)
    inputs = processor(text=[text_input], images=img_inp, videos=vid_inp,
                       padding=True, return_tensors="pt").to("cuda:0")
    n_input = int(inputs["input_ids"].shape[1])

    torch.cuda.reset_peak_memory_stats(0)
    t_start = datetime.now().isoformat()
    torch.cuda.synchronize()
    t0 = time.time()
    with torch.no_grad():
        out = model.generate(**inputs, **gen_kwargs)
    torch.cuda.synchronize()
    lat_ms = (time.time() - t0) * 1000
    t_end = datetime.now().isoformat()
    gen = out[0][n_input:]
    n_generated = int(gen.shape[0])
    raw_output = processor.decode(gen, skip_special_tokens=False)
    budget_hit = n_generated >= budget

    if is_thinking:
        answer_text, n_think, think_closed = split_think(raw_output, processor.tokenizer)
    else:
        answer_text = raw_output.replace("<|im_end|>", "").strip()
        n_think, think_closed = 0, None
    _, parse_status = parse_prediction(answer_text)
    return dict(
        arm=arm, budget=budget, sign_id=sign['sign_id'], crop_name=sign['crop_name'],
        imagePath=sign['imagePath'], n_gt=sign['n_gt'], bin=sign['bin'], seed=SEED,
        decoding=("CFG-A temp0.6/top_p0.95/top_k20/min_p0/do_sample" if is_thinking else "greedy"),
        prompt=prompt, chat_text=text_input,
        answer_text=answer_text, raw_output=raw_output, parse_status=parse_status,
        n_think_tokens=n_think, think_closed=think_closed, budget_hit=budget_hit,
        n_generated=n_generated, n_input_tokens=n_input,
        latency_ms=round(lat_ms, 1), decode_tok_s=round(n_generated / (lat_ms / 1000), 2),
        peak_alloc_gb=round(torch.cuda.max_memory_allocated(0) / 1e9, 2),
        peak_reserved_gb=round(torch.cuda.max_memory_reserved(0) / 1e9, 2),
        start_wall=t_start, end_wall=t_end,
        # token ids kept only for budget-hit thinking trials: needed for the ladder prefix check
        gen_token_ids=(gen.tolist() if (is_thinking and budget_hit) else None),
        _hardware=DEVICE_SLUG, _cuda_visible_devices=os.environ.get("CUDA_VISIBLE_DEVICES"),
        _pid=os.getpid(), _gpu_uuid=torch.cuda.get_device_properties(0).uuid.__str__(),
        attn_implementation=model.config._attn_implementation, forced_min_new_tokens=min_new_tokens,
    )


def append(trial):
    with open(TRIALS_PATH, "a") as f:
        f.write(json.dumps(trial) + "\n")
        f.flush()
        os.fsync(f.fileno())


def fmt(t):
    tc = {True: "closed", False: "OPEN", None: "-"}[t['think_closed']]
    return (f"[{t['arm']}@{t['budget']}] {t['sign_id'][:28]:28s} bin={t['bin']:5s} gen={t['n_generated']:5d} "
            f"think={t['n_think_tokens']:5d} {tc:6s} bh={t['budget_hit']} parse={t['parse_status']} "
            f"lat={t['latency_ms']/1000:.1f}s {t['decode_tok_s']}tok/s peak={t['peak_reserved_gb']}GB")


# ── Phases ─────────────────────────────────────────────────────────────────────

def run_core_arm(arm, signs, prompt, meta, core_t0):
    import torch
    done = {(t['arm'], t['budget'], t['sign_id']) for t in load_trials()}
    todo = [s for s in signs if (arm, CORE_BUDGET, s['sign_id']) not in done]
    if not todo:
        print(f"[{arm}] core already complete", flush=True)
        return True
    model, processor, info = load_model(arm)
    meta.setdefault("models", {})[arm] = info
    save_meta(meta)
    lat = []
    completed = True
    for s in todo:
        elapsed_h = (time.time() - core_t0) / 3600 + meta.get("core_elapsed_h_prior", 0.0)
        meta["core_elapsed_h"] = round(elapsed_h, 4)   # persisted so a resume continues the cap clock
        if elapsed_h > CORE_CAP_H:
            msg = f"CORE CAP HIT: {elapsed_h:.2f} h > {CORE_CAP_H} h — stopping {arm} core with partial n"
            print(msg, flush=True)
            meta.setdefault("cap_events", []).append(dict(arm=arm, at=datetime.now().isoformat(), msg=msg))
            save_meta(meta)
            completed = False
            break
        t = run_one(model, processor, s, prompt, arm, CORE_BUDGET)
        t['phase'] = "core"
        append(t)
        meta["core_elapsed_h"] = round((time.time() - core_t0) / 3600 + meta.get("core_elapsed_h_prior", 0.0), 4)
        save_meta(meta)
        lat.append(t['latency_ms'])
        print(fmt(t), flush=True)
        if len(lat) == 10:
            mean_s = sum(lat) / len(lat) / 1000
            proj_h = mean_s * len(todo) / 3600
            p = dict(arm=arm, after_trials=10, mean_s=round(mean_s, 1), projected_arm_h=round(proj_h, 2),
                     core_elapsed_h=round(elapsed_h, 2), core_cap_h=CORE_CAP_H,
                     at=datetime.now().isoformat())
            meta.setdefault("projections", []).append(p)
            save_meta(meta)
            print(f"=== PROJECTION {arm}: mean {mean_s:.1f}s/trial -> {len(todo)} trials {proj_h:.2f} h "
                  f"(core elapsed {elapsed_h:.2f} h, cap {CORE_CAP_H} h) ===", flush=True)
    del model
    torch.cuda.empty_cache()
    return completed


def run_ladder(signs, prompt, meta):
    import torch
    by_id = {s['sign_id']: s for s in signs}
    model = processor = None
    # Leftover time first completes any T32@8192 signs the 2 h core cap cut off (added 2026-10-15 during the
    # run, before the ladder phase started). Tagged phase="core_postcap": reported separately from the
    # within-cap core n, and they feed the 16384 rung like any other 8192 trial.
    rows = load_trials()
    have = {t['sign_id'] for t in rows if t['arm'] == "T32" and t['budget'] == CORE_BUDGET}
    missing = [s for s in signs if s['sign_id'] not in have]
    print(f"=== POST-CAP COMPLETION: {len(missing)} T32@{CORE_BUDGET} signs cut by the core cap; running them now ===",
          flush=True)
    meta["postcap_completion"] = dict(n=len(missing), at=datetime.now().isoformat())
    save_meta(meta)
    if missing:
        model, processor, info = load_model("T32")
        meta.setdefault("models", {})["T32_postcap"] = info
        save_meta(meta)
        for s in missing:
            t = run_one(model, processor, s, prompt, "T32", CORE_BUDGET)
            t['phase'] = "core_postcap"
            append(t)
            print(fmt(t) + " [core_postcap]", flush=True)
    prev_budget = CORE_BUDGET
    for budget in LADDER:
        rows = load_trials()
        prev = {t['sign_id']: t for t in rows if t['arm'] == "T32" and t['budget'] == prev_budget}
        done = {t['sign_id'] for t in rows if t['arm'] == "T32" and t['budget'] == budget}
        need = [sid for sid, t in prev.items() if t['think_closed'] is False]
        todo = [sid for sid in need if sid not in done]
        est_h = None
        tps = [t['decode_tok_s'] for t in rows if t['arm'] == "T32" and t['budget_hit']]
        if tps:
            est_h = len(todo) * budget / (sum(tps) / len(tps)) / 3600
        print(f"=== LADDER (leftover-time extension) rung {budget}: {len(need)} signs not closed at "
              f"{prev_budget}; {len(todo)} to run; worst-case est {est_h if est_h is None else round(est_h, 2)} h ===",
              flush=True)
        meta.setdefault("ladder_rungs", []).append(dict(budget=budget, from_budget=prev_budget, n_need=len(need),
                                                  n_todo=len(todo), worst_case_est_h=est_h,
                                                  at=datetime.now().isoformat()))
        save_meta(meta)
        if todo and model is None:
            model, processor, info = load_model("T32")
            meta.setdefault("models", {})["T32_ladder"] = info
            save_meta(meta)
        for sid in todo:
            t = run_one(model, processor, by_id[sid], prompt, "T32", budget)
            t['phase'] = "ladder_extension"
            p_ids = prev[sid].get('gen_token_ids')
            if p_ids is not None:
                new_ids = t['gen_token_ids'] if t['gen_token_ids'] is not None else None
                if new_ids is None:
                    # closed at this rung: re-tokenize not needed; compare decoded prefix instead
                    t['prefix_match'] = t['raw_output'].startswith(prev[sid]['raw_output'])
                    t['prefix_match_method'] = "decoded_text_startswith"
                else:
                    t['prefix_match'] = new_ids[:len(p_ids)] == p_ids
                    t['prefix_match_method'] = "token_ids"
                if not t['prefix_match']:
                    # first divergence position (text), for the report
                    a, b = prev[sid]['raw_output'], t['raw_output']
                    k = next((i for i in range(min(len(a), len(b))) if a[i] != b[i]), min(len(a), len(b)))
                    t['prefix_diverge_char'] = k
            append(t)
            print(fmt(t) + f" prefix_match={t.get('prefix_match')}", flush=True)
        prev_budget = budget
    if model is not None:
        del model
        torch.cuda.empty_cache()


def run_longdiag(signs, prompt, meta):
    """Step 2 (2026-10-15): re-run the 8 long-budget SDPA traces (6 @16384, 2 @24576; same sign, budget,
    seed) under flash-attn, plus one forced-length probe at 24,576 (min_new_tokens) so the 24,576 peak is
    measured even if the flash-attn trace terminates earlier. The allocator cache is emptied before each
    trace so peak_reserved is per-trace, not inherited from earlier trials."""
    import torch
    by_id = {s['sign_id']: s for s in signs}
    sdpa = [json.loads(l) for l in open(SDPA_TRIALS_PATH)]
    long_sdpa = sorted((t for t in sdpa if t['arm'] == "T32" and t['budget'] > CORE_BUDGET),
                       key=lambda t: -t['budget'])
    jobs = [(t['sign_id'], t['budget'], None) for t in long_sdpa]
    probe_sign = next(t['sign_id'] for t in long_sdpa if t['budget'] == 24576)
    jobs.insert(2, (probe_sign, 24576, 24576))   # after the two natural 24,576 traces
    done = set()
    if LONGDIAG_PATH.exists():
        done = {(t['sign_id'], t['budget'], t.get('forced_min_new_tokens')) for t in map(json.loads, open(LONGDIAG_PATH))}
    print(f"=== LONGDIAG: {len(jobs)} jobs ({len(long_sdpa)} SDPA long traces + 1 forced 24,576 probe) ===", flush=True)
    model, processor, info = load_model("T32")
    meta.setdefault("models", {})["T32_longdiag"] = info
    save_meta(meta)
    for sid, budget, forced in jobs:
        if (sid, budget, forced) in done:
            continue
        torch.cuda.empty_cache()
        t = run_one(model, processor, by_id[sid], prompt, "T32", budget, min_new_tokens=forced)
        t['phase'] = "longdiag_forced" if forced else "longdiag"
        with open(LONGDIAG_PATH, "a") as f:
            f.write(json.dumps(t) + "\n")
        print(fmt(t) + f" [{t['phase']}] alloc={t['peak_alloc_gb']}GB", flush=True)
    del model
    torch.cuda.empty_cache()


def main():
    global ATTN, TRIALS_PATH, META_PATH, CORE_CAP_H
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["core", "ladder", "all", "longdiag"], default="all")
    ap.add_argument("--attn", choices=["flash_attention_2", "sdpa"], default="flash_attention_2")
    ap.add_argument("--dry-run", action="store_true",
                    help="CPU only: build manifest/crops/prompt and exercise parsing; no model")
    args = ap.parse_args()
    ATTN = args.attn
    if ATTN == "flash_attention_2":
        TRIALS_PATH = OUT_DIR / f"study_t_trials_{DEVICE_SLUG}_fa2.jsonl"
        META_PATH = OUT_DIR / f"study_t_run_meta_{DEVICE_SLUG}_fa2.json"
        CORE_CAP_H = float("inf")  # no time restriction for the flash-attn re-run (user, 2026-10-15)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    prompt = make_prompt()
    signs = load_signs()
    print(f"{len(signs)} signs; bins " +
          str({b: sum(s['bin'] == b for s in signs) for b in ("low", "mid", "high", "other")}), flush=True)

    if args.dry_run:
        print("prompt sha256", hashlib.sha256(prompt.encode()).hexdigest()[:16], "len", len(prompt))
        print("crop sizes", [s['img'].size for s in signs[:5]])
        for txt in ['```json\n{"T": {"left": "Changi"}, "S": {}}\n```<|im_end|>', "garbage"]:
            print("parse", repr(txt[:30]), parse_prediction(txt))
        return

    import torch
    import transformers
    assert torch.cuda.device_count() >= 1
    print(f"cuda:0 = {torch.cuda.get_device_name(0)}; transformers {transformers.__version__}; "
          f"torch {torch.__version__}; CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES')}", flush=True)
    import subprocess
    meta = load_meta()
    meta.update(
        study="StudyT", device=DEVICE_SLUG, gpu=torch.cuda.get_device_name(0),
        transformers=transformers.__version__, torch=torch.__version__,
        dataset=HF_REPO, dataset_sha=HF_REPO_SHA,
        sign_understanding_commit=subprocess.run(["git", "-C", "/tmp/sign-understanding", "rev-parse", "HEAD"],
                                                 capture_output=True, text=True).stdout.strip(),
        manifest=J2_MANIFEST, n_signs=len(signs), seed=SEED, core_budget=CORE_BUDGET, ladder=list(LADDER),
        attn_implementation=ATTN, core_cap_h=str(CORE_CAP_H), prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
        thinking_gen=THINKING_GEN, instruct_gen=INSTRUCT_GEN,
    )
    save_meta(meta)

    if args.phase == "longdiag":
        run_longdiag(signs, prompt, meta)
        print("done", flush=True)
        return
    if args.phase in ("core", "all"):
        core_t0 = time.time()
        meta["core_elapsed_h_prior"] = meta.get("core_elapsed_h", 0.0)
        for arm in ("I32", "T32"):
            ok = run_core_arm(arm, signs, prompt, meta, core_t0)
            if not ok:
                break
        meta["core_finished_at"] = datetime.now().isoformat()
        save_meta(meta)
    if args.phase in ("ladder", "all"):
        run_ladder(signs, prompt, meta)
        meta["ladder_finished_at"] = datetime.now().isoformat()
        save_meta(meta)
    print("done", flush=True)


if __name__ == "__main__":
    main()
