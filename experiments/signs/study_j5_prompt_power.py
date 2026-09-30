"""
StudyJ5 — Properly powered prompt comparison.

Tests whether the simplified prompt (StudyJ3 arm B) significantly reduces
non-termination vs the original paper prompt across 14 signs × 5 seeds.

ORIGINAL arm (70 trials): fully reused from StudyJ4.
SIMPLIFIED arm (70 trials): fresh inference.

Writes:
  results/signs/study_j5/study_j5_trials.jsonl
"""
import sys, json, os, time, ast, re, argparse
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

TRIALS_PATH   = "results/signs/study_j5/study_j5_trials.jsonl"
J4_PATH       = "results/signs/study_j4/study_j4_trials.jsonl"

MAX_NEW_TOKENS    = 24576
DIRECTIONS        = ['left', 'right', 'straight', 'straight-right', 'straight-left', 'locational']
BUDGET_STOP_HOURS = 14.0
SEEDS             = [42, 123, 456, 789, 1011]

GEN_KWARGS = dict(
    do_sample=True, temperature=0.6, top_p=0.95, top_k=20, min_p=0.0,
    max_new_tokens=MAX_NEW_TOKENS,
)

# 14 signs — same as StudyJ4
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
CONTROL_CROPS = [
    ('IMG_0049_frame_0003_0.jpg', 1, 'low'),
    ('IMG_0064_frame_0003_1.jpg', 1, 'low'),
    ('IMG_6567_frame_0017_0.jpg', 3, 'mid'),
    ('IMG_0042_frame_0022_0.jpg', 5, 'mid'),
    ('IMG_6415_frame_0015_0.jpg', 7, 'high'),
    ('IMG_6584_frame_0019_0.jpg', 18, 'high'),
]
ALL_CROPS = CAP_HIT_CROPS + CONTROL_CROPS


def make_prompts():
    raw     = open(PROMPT_PATH).read()
    symbols = [l.strip() for l in open(SYMBOLS_PATH) if l.strip()]
    sym_str = ", ".join(symbols[:10])

    original = (raw
        .replace("GT_SYMBOL_LIST", sym_str)
        .replace("REPLACE_DIRECTION_LIST", str(DIRECTIONS)))

    simplified = f"""I'll teach you how to read navigational signs today. There are 2 important components of any sign: the text or symbol corresponding to the location and the arrow describing the direction you need to move in, as if you are standing in front of the board, in order to reach the location.

If you see location names besides these arrows then specify the direction of the arrow as it would look if you were standing perfectly in front of the sign board.
If you see symbols on the navigational sign then use your commonsense understanding of the symbol image and the text around it to convert it to text name for representing as a location name. Some examples of such locations could be -- {sym_str}. Use your commonsense understanding to decode such common symbols observed in navigational signs to locations.

Now I will teach you how to read arrows. We need to read the arrows in the frame of the navigation signboard.

If it points north then we say it points to the direction "straight".
If it points east wrt to the board, we say it points to "right".
If it points west wrt to the board we say it points to "left"
If it points diagonally north-east wrt to the board we say it points to "straight-right"
If it points diagonally north-west wrt to the board we say it points to "straight-left"
If there is some information on the navigation board with NO ARROWS associated with it, then respond the arrow direction as "locational" for that location text.

The output direction should be from this list {DIRECTIONS}. Return a JSON dictionary with keys "t" or "s" based on whether the location name was inferred through text ("t") or through symbol ("s"), with values as another dictionary mapping location names to arrow directions.
Only consider English text. Ignore other languages. No extra text except the dictionary."""

    return original, simplified


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
                done.add((t['crop_name'], t['arm'], t['seed']))
            except Exception:
                pass
    return done


def load_j4_original():
    """Load all StudyJ4 trials to reuse as ORIGINAL arm."""
    reused = {}
    if not os.path.exists(J4_PATH):
        return reused
    for line in open(J4_PATH):
        t = json.loads(line)
        if 'error' in t: continue
        key = (t['crop_name'], t['seed'])
        reused[key] = t
    return reused


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    original_prompt, simplified_prompt = make_prompts()
    gt_map = load_gt_map()

    # Build full run list: ORIGINAL reused + SIMPLIFIED fresh
    runs = []
    for crop, n_gt, bin_ in ALL_CROPS:
        role = 'cap_hit' if (crop, n_gt, bin_) in [(c,n,b) for c,n,b in CAP_HIT_CROPS] else 'control'
        for seed in SEEDS:
            runs.append({'crop': crop, 'n_gt': n_gt, 'bin': bin_, 'seed': seed,
                         'role': role, 'arm': 'ORIGINAL'})
            runs.append({'crop': crop, 'n_gt': n_gt, 'bin': bin_, 'seed': seed,
                         'role': role, 'arm': 'SIMPLIFIED'})

    print(f"Total planned runs: {len(runs)} (70 ORIGINAL + 70 SIMPLIFIED)")

    j4_reuse = load_j4_original()
    print(f"J4 trials available for reuse: {len(j4_reuse)}")

    if args.dry_run:
        fresh = [r for r in runs if r['arm']=='SIMPLIFIED']
        print(f"Fresh SIMPLIFIED runs needed: {len(fresh)}")
        print("--dry-run: exiting.")
        return

    os.makedirs(os.path.dirname(TRIALS_PATH), exist_ok=True)
    done = already_done(TRIALS_PATH)

    out_f = open(TRIALS_PATH, 'a')
    reused_written = 0

    # Write ORIGINAL arm from J4 reuse
    for run in runs:
        if run['arm'] != 'ORIGINAL': continue
        key = (run['crop'], run['seed'])
        if (run['crop'], 'ORIGINAL', run['seed']) in done: continue
        if key not in j4_reuse:
            print(f"WARNING: J4 trial missing for {run['crop']} seed={run['seed']} — will run fresh")
            continue
        src = j4_reuse[key]
        trial = {
            'crop_name': run['crop'], 'imagePath': src.get('imagePath',''),
            'objectID': src.get('objectID', 0),
            'n_gt': run['n_gt'], 'bin': run['bin'], 'role': run['role'],
            'arm': 'ORIGINAL', 'seed': run['seed'],
            'n_input_tokens': src.get('n_input_tokens', 0),
            'n_generated_tokens': src.get('n_generated_tokens', 0),
            'n_think_tokens': src.get('n_think_tokens', 0),
            'n_answer_tokens': src.get('n_answer_tokens', 0),
            'total_latency_ms': src.get('total_latency_ms', 0),
            'truncated': src.get('truncated', False),
            'think_closed': src.get('think_closed', False),
            'parse_status': src.get('parse_status', 'unknown'),
            'prediction': src.get('prediction'),
            'last_500_tokens': src.get('last_500_tokens', ''),
            'reused_from': 'StudyJ4',
            'max_new_tokens': MAX_NEW_TOKENS,
        }
        out_f.write(json.dumps(trial) + '\n')
        out_f.flush()
        done.add((run['crop'], 'ORIGINAL', run['seed']))
        reused_written += 1

    print(f"ORIGINAL arm written (reused from J4): {reused_written}/70")

    # Fresh SIMPLIFIED runs
    fresh_runs = [r for r in runs
                  if r['arm'] == 'SIMPLIFIED'
                  and (r['crop'], r['arm'], r['seed']) not in done]
    print(f"Fresh SIMPLIFIED runs needed: {len(fresh_runs)}")

    if not fresh_runs:
        print("All runs done.")
        out_f.close()
        return

    print("Loading model...", flush=True)
    model     = Qwen3VLForConditionalGeneration.from_pretrained(
        THINKING_PATH, torch_dtype=torch.bfloat16, device_map=DEVICE)
    model.eval()
    processor = AutoProcessor.from_pretrained(THINKING_PATH)

    hf_cache    = {}
    lat_history = []
    run_idx     = 0
    seeds_reduced = False

    for run in fresh_runs:
        if (run['crop'], run['arm'], run['seed']) in done:
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
                                                    {"type": "text", "text": simplified_prompt}]}]
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
                'arm': 'SIMPLIFIED', 'seed': run['seed'],
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
            done.add((crop, 'SIMPLIFIED', run['seed']))

            lat_history.append(lat_ms)
            status = "TRUNC" if truncated else f"ok({n_think}tok)"
            print(f"[{run_idx}] {crop[:22]}  n_gt={run['n_gt']}  seed={run['seed']}  "
                  f"gen={len(generated)}  trunc={truncated}  closed={think_closed}  "
                  f"lat={lat_ms/1000:.1f}s  {status}", flush=True)

            # Projection after 5 fresh runs
            if len(lat_history) == 5:
                mean_ms   = sum(lat_history) / len(lat_history)
                remaining = len(fresh_runs) - run_idx
                proj_h    = (mean_ms * remaining) / 3_600_000
                print(f"\n=== RUNTIME PROJECTION (after 5 fresh runs) ===")
                print(f"Mean lat: {mean_ms/1000:.1f}s  Remaining: {remaining}  Projected: {proj_h:.1f}h")
                if proj_h > BUDGET_STOP_HOURS:
                    print(f"Projection {proj_h:.1f}h > {BUDGET_STOP_HOURS}h — REDUCING TO 3 SEEDS (42,123,456)")
                    seeds_reduced = True
                    skip_seeds = {789, 1011}
                    fresh_runs = [r for r in fresh_runs[run_idx:] if r['seed'] not in skip_seeds]
                    run_idx = 0
                    print(f"Remaining after reduction: {len(fresh_runs)}")
                else:
                    print(f"Within {BUDGET_STOP_HOURS}h. Continuing with all 5 seeds.")
                print("================================================\n", flush=True)

        except Exception as e:
            trial = {'crop_name': crop, 'n_gt': run['n_gt'], 'bin': run['bin'],
                     'role': run['role'], 'arm': 'SIMPLIFIED', 'seed': run['seed'],
                     'error': str(e), 'truncated': False, 'think_closed': False,
                     'reused_from': None, 'max_new_tokens': MAX_NEW_TOKENS}
            out_f.write(json.dumps(trial) + '\n')
            out_f.flush()
            print(f"[{run_idx}] ERROR {crop} seed={run['seed']}  {e}", flush=True)

    out_f.close()
    if seeds_reduced:
        print("\nNOTE: Seeds reduced to [42,123,456] due to runtime projection.")
    total = sum(1 for _ in open(TRIALS_PATH))
    print(f"\nDone. {total} trials written to {TRIALS_PATH}")


if __name__ == "__main__":
    main()
