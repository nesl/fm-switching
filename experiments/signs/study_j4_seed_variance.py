"""
StudyJ4 — Seed variance on SiGNgapore2D non-terminators.

Tests whether non-termination is INPUT-DETERMINED (bimodal: signs are either
always-fail or always-succeed) or STOCHASTIC (per-attempt failure rate, sign-agnostic).

Subjects: 8 cap-hit signs from StudyJ2 + 6 control completers.
Seeds: 42, 123, 456, 789, 1011 (5 draws per sign = 70 total runs).
Seeds 42 (StudyJ2) and 123 (StudyJ3 arm A) reused where code path identical.

Writes:
  results/signs/study_j4/study_j4_trials.jsonl
"""
import sys, json, os, time, random, ast, re, argparse
import torch
sys.path.insert(0, '/tmp/sign-understanding')
from PIL import Image
from huggingface_hub import hf_hub_download
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
from qwen_vl_utils import process_vision_info

THINKING_PATH = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Thinking/snapshots/1de27d8c51f12e819435303b9e84c4e25ba8401e"
DEVICE        = "cuda:1"
HF_REPO       = "NickyZimmerman/SiGNgapore2D"
GT_PATH       = "/tmp/sign-understanding/gt/gt_annotation.json"
EXCLUDE_PATH  = "/tmp/sign-understanding/gt/recognition-exclude-imgs.txt"
PROMPT_PATH   = "/tmp/sign-understanding/prompts/prompt.txt"
SYMBOLS_PATH  = "/tmp/sign-understanding/prompts/symbols.txt"

TRIALS_PATH   = "results/signs/study_j4/study_j4_trials.jsonl"

MAX_NEW_TOKENS   = 24576
DIRECTIONS       = ['left', 'right', 'straight', 'straight-right', 'straight-left', 'locational']
BUDGET_STOP_HOURS = 14.0
FALLBACK_SEEDS   = [42, 123, 456]   # used if projection >14h

GEN_KWARGS = dict(
    do_sample=True, temperature=0.6, top_p=0.95, top_k=20, min_p=0.0,
    max_new_tokens=MAX_NEW_TOKENS,
)

# 8 cap-hit signs from StudyJ2
CAP_HIT_CROPS = [
    ('IMG_6416_frame_0013_0.jpg', 3, 'mid'),
    ('IMG_6546_frame_0019_1.jpg', 4, 'mid'),
    ('IMG_6617_frame_0015_0.jpg', 5, 'mid'),
    ('IMG_6548_frame_0019_1.jpg', 4, 'mid'),
    ('IMG_6623_frame_0015_0.jpg', 7, 'high'),
    ('IMG_6411_frame_0014_0.jpg', 3, 'mid'),
    ('IMG_0037_frame_0014_0.jpg', 7, 'high'),
    ('IMG_0068_frame_0007_0.jpg', 7, 'high'),
]

# 6 control completers from StudyJ2 manifest (seed=99 sample, 2 per bin)
CONTROL_CROPS = [
    ('IMG_0049_frame_0003_0.jpg', 1, 'low'),
    ('IMG_0064_frame_0003_1.jpg', 1, 'low'),
    ('IMG_6567_frame_0017_0.jpg', 3, 'mid'),
    ('IMG_0042_frame_0022_0.jpg', 5, 'mid'),
    ('IMG_6415_frame_0015_0.jpg', 7, 'high'),
    ('IMG_6584_frame_0019_0.jpg', 18, 'high'),
]

FULL_SEEDS    = [42, 123, 456, 789, 1011]

# Trials that can be reused from prior studies (same model, same prompt, same decoding)
# StudyJ2: seed=42, all cap-hit crops
# StudyJ3 arm A (ORIGINAL-SEED123): seed=123, all 12 signs (cap-hits + J3 controls)
# Note: J3 controls differ from J4 controls — no overlap to reuse there.
REUSABLE = {
    # (crop, seed): (source_study, source_path)
    **{(crop, 42):  ('StudyJ2', 'results/signs/study_j2/study_j2_trials.jsonl') for crop,_,_ in CAP_HIT_CROPS},
    **{(crop, 123): ('StudyJ3-armA', 'results/signs/study_j3/study_j3_trials.jsonl') for crop,_,_ in CAP_HIT_CROPS},
}


def load_reused_trials():
    """Load existing trial data that can be reused, keyed by (crop, seed)."""
    reused = {}

    # From StudyJ2 (seed=42, cap-hits only)
    j2_path = 'results/signs/study_j2/study_j2_trials.jsonl'
    if os.path.exists(j2_path):
        for line in open(j2_path):
            t = json.loads(line)
            key = (t['crop_name'], 42)
            if key in REUSABLE:
                reused[key] = {**t, 'reused_from': 'StudyJ2', 'seed': 42}

    # From StudyJ3 arm A (seed=123, cap-hits + J3-specific controls)
    j3_path = 'results/signs/study_j3/study_j3_trials.jsonl'
    if os.path.exists(j3_path):
        for line in open(j3_path):
            t = json.loads(line)
            if t.get('arm') == 'ORIGINAL-SEED123':
                key = (t['crop_name'], 123)
                if key in REUSABLE:
                    reused[key] = {**t, 'reused_from': 'StudyJ3-armA', 'seed': 123}

    return reused


def load_gt_map():
    gt      = json.load(open(GT_PATH))
    exclude = set(l.strip() for l in open(EXCLUDE_PATH) if l.strip())
    m = {}
    for entry in gt:
        stem = entry['imagePath'][:-4]
        for i, ann in enumerate(entry['annotation']):
            tl = ann.get('text labels', {}); sl = ann.get('symbol labels', {}); mx = ann.get('mixed', {}) or {}
            if tl == {} and sl == {} and mx == {}: continue
            crop = f'{stem}_{i}.jpg'
            if crop in exclude: continue
            n_gt = len(tl) + len(sl) - len(mx)
            m[crop] = {'imagePath': entry['imagePath'], 'objectID': i,
                       'bbox': ann['boundingBox'], 'n_gt': n_gt,
                       'text_labels': tl, 'symbol_labels': sl, 'mixed': mx}
    return m


def crop_bbox(img, bbox):
    cx, cy, w, h = bbox
    return img.crop((max(0,int(cx-w/2)), max(0,int(cy-h/2)),
                     min(img.width,int(cx+w/2)), min(img.height,int(cy+h/2))))


def make_prompt():
    raw     = open(PROMPT_PATH).read()
    symbols = [l.strip() for l in open(SYMBOLS_PATH) if l.strip()]
    sym_str = ", ".join(symbols[:10])
    return (raw
        .replace("GT_SYMBOL_LIST", sym_str)
        .replace("REPLACE_DIRECTION_LIST", str(DIRECTIONS)))


def extract_think_and_answer(full_output, processor):
    if "</think>" in full_output:
        think_part, answer_part = full_output.split("</think>", 1)
        think_content = think_part.replace("<think>", "").strip()
        answer_text   = answer_part.strip()
        think_closed  = True
    else:
        think_content = full_output.replace("<think>", "").strip()
        answer_text   = ""
        think_closed  = False
    n_think  = len(processor.tokenizer.encode(think_content, add_special_tokens=False)) if think_content else 0
    n_answer = len(processor.tokenizer.encode(answer_text,   add_special_tokens=False)) if answer_text   else 0
    return think_content, answer_text, n_think, n_answer, think_closed


def parse_prediction(answer_text):
    text = re.sub(r"```(?:json)?", "", answer_text).strip().strip("`").strip()
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


def already_done(path):
    done = set()
    if os.path.exists(path):
        for line in open(path):
            try:
                t = json.loads(line)
                done.add((t['crop_name'], t['seed']))
            except Exception:
                pass
    return done


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    all_crops = CAP_HIT_CROPS + CONTROL_CROPS  # 14 signs
    seeds     = FULL_SEEDS                       # 5 seeds; may reduce to 3 after projection

    # Build run list
    runs = []
    for crop, n_gt, bin_ in all_crops:
        role = 'cap_hit' if (crop, n_gt, bin_) in [(c,n,b) for c,n,b in CAP_HIT_CROPS] else 'control'
        for seed in seeds:
            runs.append({'crop': crop, 'n_gt': n_gt, 'bin': bin_, 'seed': seed, 'role': role})

    print(f"Total planned runs: {len(runs)} ({len(all_crops)} signs × {len(seeds)} seeds)")

    reused = load_reused_trials()
    print(f"Reusable trials found: {len(reused)} (StudyJ2 seed=42 cap-hits + StudyJ3-armA seed=123 cap-hits)")

    if args.dry_run:
        fresh_runs = [r for r in runs if (r['crop'], r['seed']) not in reused]
        print(f"Fresh runs needed: {len(fresh_runs)}")
        print("--dry-run: exiting.")
        return

    os.makedirs(os.path.dirname(TRIALS_PATH), exist_ok=True)
    done = already_done(TRIALS_PATH)

    # Write reused trials first (if not already done)
    out_f = open(TRIALS_PATH, 'a')
    reused_written = 0
    for (crop, seed), t in reused.items():
        if (crop, seed) not in done:
            trial = {
                'crop_name': crop, 'imagePath': t.get('imagePath',''),
                'objectID': t.get('objectID', 0),
                'n_gt': t['n_gt'], 'bin': next((b for c,n,b in all_crops if c==crop), 'unknown'),
                'role': 'cap_hit',
                'seed': seed,
                'n_input_tokens': t.get('n_input_tokens', 0),
                'n_generated_tokens': t.get('n_generated_tokens', 0),
                'n_think_tokens': t.get('n_think_tokens', 0),
                'n_answer_tokens': t.get('n_answer_tokens', 0),
                'total_latency_ms': t.get('total_latency_ms', 0),
                'truncated': t.get('truncated', False),
                'think_closed': t.get('think_closed', False),
                'parse_status': t.get('parse_status', 'unknown'),
                'prediction': t.get('prediction'),
                'last_500_tokens': t.get('last_500_tokens', ''),
                'reused_from': t['reused_from'],
                'max_new_tokens': MAX_NEW_TOKENS,
            }
            out_f.write(json.dumps(trial) + '\n')
            out_f.flush()
            done.add((crop, seed))
            reused_written += 1
    print(f"Reused trials written: {reused_written}")

    # Load model for fresh runs
    fresh_runs = [r for r in runs if (r['crop'], r['seed']) not in done]
    print(f"Fresh runs needed: {len(fresh_runs)}")
    if not fresh_runs:
        print("All runs already done.")
        out_f.close()
        return

    prompt  = make_prompt()
    gt_map  = load_gt_map()

    print("Loading model...", flush=True)
    model     = Qwen3VLForConditionalGeneration.from_pretrained(
        THINKING_PATH, torch_dtype=torch.bfloat16, device_map=DEVICE)
    model.eval()
    processor = AutoProcessor.from_pretrained(THINKING_PATH)

    hf_cache   = {}
    lat_history = []
    run_idx     = 0
    seeds_reduced = False

    for run in fresh_runs:
        if (run['crop'], run['seed']) in done:
            continue

        run_idx += 1
        crop = run['crop']
        info = gt_map.get(crop)
        if info is None:
            print(f"WARNING: {crop} not in gt_map — skipping", flush=True)
            continue

        if info['imagePath'] not in hf_cache:
            local = hf_hub_download(repo_id=HF_REPO, filename=f"images/{info['imagePath']}", repo_type="dataset")
            hf_cache[info['imagePath']] = Image.open(local).convert("RGB")
        img = crop_bbox(hf_cache[info['imagePath']], info['bbox'])

        torch.manual_seed(run['seed'])
        messages   = [{"role": "user", "content": [{"type": "image", "image": img},
                                                    {"type": "text", "text": prompt}]}]
        text_input = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        img_inp, vid_inp = process_vision_info(messages)
        inputs = processor(text=[text_input], images=img_inp, videos=vid_inp,
                           padding=True, return_tensors="pt").to(DEVICE)
        n_input = inputs["input_ids"].shape[1]

        t0 = time.time()
        try:
            with torch.no_grad():
                output_ids = model.generate(**inputs, **GEN_KWARGS)
            generated = output_ids[0][n_input:]
            lat_ms    = (time.time() - t0) * 1000

            full_output = processor.decode(generated, skip_special_tokens=False)
            truncated   = len(generated) >= MAX_NEW_TOKENS

            think_content, answer_text, n_think, n_answer, think_closed = \
                extract_think_and_answer(full_output, processor)

            prediction, parse_status = parse_prediction(answer_text)

            last_500 = ""
            if truncated:
                last_500 = processor.decode(generated[-500:], skip_special_tokens=False)

            trial = {
                'crop_name': crop, 'imagePath': info['imagePath'],
                'objectID': info['objectID'],
                'n_gt': run['n_gt'], 'bin': run['bin'], 'role': run['role'],
                'seed': run['seed'],
                'n_input_tokens': n_input, 'n_generated_tokens': len(generated),
                'n_think_tokens': n_think, 'n_answer_tokens': n_answer,
                'total_latency_ms': lat_ms,
                'truncated': truncated, 'think_closed': think_closed,
                'parse_status': parse_status, 'prediction': prediction,
                'last_500_tokens': last_500,
                'reused_from': None,
                'max_new_tokens': MAX_NEW_TOKENS,
            }
            out_f.write(json.dumps(trial) + '\n')
            out_f.flush()
            done.add((crop, run['seed']))

            lat_history.append(lat_ms)
            status = "TRUNC" if truncated else f"ok({n_think}tok)"
            print(f"[{run_idx}] {crop}  n_gt={run['n_gt']}  role={run['role']}  seed={run['seed']}  "
                  f"gen={len(generated)}  trunc={truncated}  closed={think_closed}  "
                  f"lat={lat_ms/1000:.1f}s  {status}", flush=True)

            # Projection after 5 fresh runs
            if len(lat_history) == 5:
                mean_ms   = sum(lat_history) / len(lat_history)
                remaining = len(fresh_runs) - run_idx
                proj_h    = (mean_ms * remaining) / 3_600_000
                total_fresh_h = (mean_ms * len(fresh_runs)) / 3_600_000
                print(f"\n=== RUNTIME PROJECTION (after 5 fresh runs) ===")
                print(f"Mean lat: {mean_ms/1000:.1f}s  Remaining fresh: {remaining}  Projected: {proj_h:.1f}h (total fresh: {total_fresh_h:.1f}h)")
                if proj_h > BUDGET_STOP_HOURS:
                    print(f"Projection {proj_h:.1f}h > {BUDGET_STOP_HOURS}h limit — REDUCING TO 3 SEEDS (42,123,456)")
                    seeds_reduced = True
                    skip_seeds = {789, 1011}
                    fresh_runs = [r for r in fresh_runs[run_idx:] if r['seed'] not in skip_seeds]
                    run_idx = 0
                    print(f"Remaining after reduction: {len(fresh_runs)} runs")
                else:
                    print(f"Within {BUDGET_STOP_HOURS}h. Continuing with all 5 seeds.")
                print("================================================\n", flush=True)

        except Exception as e:
            trial = {'crop_name': crop, 'n_gt': run['n_gt'], 'bin': run['bin'],
                     'role': run['role'], 'seed': run['seed'],
                     'error': str(e), 'truncated': False, 'think_closed': False,
                     'reused_from': None, 'max_new_tokens': MAX_NEW_TOKENS}
            out_f.write(json.dumps(trial) + '\n')
            out_f.flush()
            print(f"[{run_idx}] ERROR {crop} seed={run['seed']}  {e}", flush=True)

    out_f.close()
    if seeds_reduced:
        print("\nNOTE: Seeds reduced to [42,123,456] due to runtime projection exceeding 14h limit.")
    print(f"\nDone. Trials written to {TRIALS_PATH}")


if __name__ == "__main__":
    main()
