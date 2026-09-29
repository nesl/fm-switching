"""
StudyJ2 — Survival curve of reasoning length on SiGNgapore2D.

40-sign stratified subset (seed=42 manifest pre-written before inference).
max_new_tokens=24576, same decoding as StudyJ.
skip_special_tokens=False for accurate </think> detection.

Writes:
  results/signs/study_j2/manifest.json   (40-sign manifest, written before inference)
  results/signs/study_j2/study_j2_trials.jsonl  (one JSON per line)
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

MANIFEST_PATH = "results/signs/study_j2/manifest.json"
TRIALS_PATH   = "results/signs/study_j2/study_j2_trials.jsonl"

MAX_NEW_TOKENS = 24576
SEED           = 42
DIRECTIONS     = ['left', 'right', 'straight', 'straight-right', 'straight-left', 'locational']
BUDGET_STOP_HOURS = 8.0

GEN_KWARGS = dict(
    do_sample=True, temperature=0.6, top_p=0.95, top_k=20, min_p=0.0,
    max_new_tokens=MAX_NEW_TOKENS,
)


def load_gt_map():
    gt      = json.load(open(GT_PATH))
    exclude = set(l.strip() for l in open(EXCLUDE_PATH) if l.strip())
    signs   = []
    for entry in gt:
        stem = entry['imagePath'][:-4]
        for i, ann in enumerate(entry['annotation']):
            tl = ann.get('text labels', {})
            sl = ann.get('symbol labels', {})
            mx = ann.get('mixed', {}) or {}
            if tl == {} and sl == {} and mx == {}:
                continue
            crop = f'{stem}_{i}.jpg'
            if crop in exclude:
                continue
            n_gt = len(tl) + len(sl) - len(mx)
            signs.append({
                'crop': crop, 'imagePath': entry['imagePath'],
                'objectID': i, 'bbox': ann['boundingBox'], 'n_gt': n_gt,
            })
    return signs


def build_manifest(signs, seed=42):
    rng  = random.Random(seed)
    low  = [s for s in signs if 1 <= s['n_gt'] <= 2]
    mid  = [s for s in signs if 3 <= s['n_gt'] <= 5]
    high = [s for s in signs if s['n_gt'] >= 6]
    other = [s for s in signs if s['n_gt'] <= 0]
    sel_low   = rng.sample(low,   13)
    sel_mid   = rng.sample(mid,   13)
    sel_high  = rng.sample(high,  13)
    sel_other = rng.sample(other,  1)
    manifest = sel_low + sel_mid + sel_high + sel_other
    rng.shuffle(manifest)
    return manifest


def load_prompt():
    text    = open(PROMPT_PATH).read()
    symbols = [l.strip() for l in open(SYMBOLS_PATH) if l.strip()]
    text    = text.replace("GT_SYMBOL_LIST", ", ".join(symbols[:10]))
    text    = text.replace("REPLACE_DIRECTION_LIST", str(DIRECTIONS))
    return text


def crop_bbox(img, bbox):
    cx, cy, w, h = bbox
    x1 = max(0, int(cx - w/2)); y1 = max(0, int(cy - h/2))
    x2 = min(img.width, int(cx + w/2)); y2 = min(img.height, int(cy + h/2))
    return img.crop((x1, y1, x2, y2))


def extract_think_and_answer(full_output, processor):
    """
    skip_special_tokens=False: both <think> and </think> appear in raw output.
    Split on </think> to separate think from answer.
    """
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
                done.add(t['crop_name'])
            except Exception:
                pass
    return done


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-manifest', action='store_true', help='Build and write manifest only, then exit')
    args = parser.parse_args()

    # --- build/load manifest ---
    signs = load_gt_map()
    manifest = build_manifest(signs, seed=SEED)

    if not os.path.exists(MANIFEST_PATH):
        os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
        json.dump(manifest, open(MANIFEST_PATH, 'w'), indent=2)
        print(f"Manifest written: {MANIFEST_PATH}  ({len(manifest)} signs)")
    else:
        loaded = json.load(open(MANIFEST_PATH))
        if [s['crop'] for s in loaded] != [s['crop'] for s in manifest]:
            print("WARNING: manifest on disk differs from freshly generated one. Using on-disk version.")
            manifest = loaded
        print(f"Manifest loaded: {MANIFEST_PATH}  ({len(manifest)} signs)")

    print("Bin counts in manifest:")
    for bin_name, lo, hi in [('low(1-2)', 1, 2), ('mid(3-5)', 3, 5), ('high(6+)', 6, 999), ('other(<=0)', -99, 0)]:
        n = sum(1 for s in manifest if lo <= s['n_gt'] <= hi)
        print(f"  {bin_name}: {n}")

    if args.dry_manifest:
        print("--dry-manifest: exiting before model load.")
        return

    # --- load model ---
    print("Loading Qwen3-VL-4B-Thinking ...", flush=True)
    model     = Qwen3VLForConditionalGeneration.from_pretrained(
        THINKING_PATH, torch_dtype=torch.bfloat16, device_map=DEVICE)
    model.eval()
    processor = AutoProcessor.from_pretrained(THINKING_PATH)

    prompt    = load_prompt()
    hf_cache  = {}
    done      = already_done(TRIALS_PATH)
    out_f     = open(TRIALS_PATH, 'a')

    print(f"Already done: {len(done)}/{len(manifest)}", flush=True)

    latency_history = []

    for idx, sign in enumerate(manifest):
        if sign['crop'] in done:
            print(f"[{idx+1}/{len(manifest)}] SKIP (already done): {sign['crop']}", flush=True)
            continue

        # load image
        if sign['imagePath'] not in hf_cache:
            local = hf_hub_download(repo_id=HF_REPO, filename=f"images/{sign['imagePath']}", repo_type="dataset")
            hf_cache[sign['imagePath']] = Image.open(local).convert("RGB")
        img = crop_bbox(hf_cache[sign['imagePath']], sign['bbox'])

        torch.manual_seed(SEED)
        messages    = [{"role": "user", "content": [{"type": "image", "image": img}, {"type": "text", "text": prompt}]}]
        text_input  = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = process_vision_info(messages)
        inputs      = processor(text=[text_input], images=image_inputs, videos=video_inputs,
                                padding=True, return_tensors="pt").to(DEVICE)
        n_input     = inputs["input_ids"].shape[1]

        t0 = time.time()
        try:
            with torch.no_grad():
                output_ids = model.generate(**inputs, **GEN_KWARGS)
            generated  = output_ids[0][n_input:]
            t1         = time.time()
            latency_ms = (t1 - t0) * 1000

            # decode with skip_special_tokens=False for accurate </think> detection
            full_output = processor.decode(generated, skip_special_tokens=False)
            truncated   = len(generated) >= MAX_NEW_TOKENS

            think_content, answer_text, n_think, n_answer, think_closed = extract_think_and_answer(
                full_output, processor)

            prediction, parse_status = parse_prediction(answer_text)

            trial = {
                'crop_name': sign['crop'],
                'imagePath': sign['imagePath'],
                'objectID':  sign['objectID'],
                'n_gt':      sign['n_gt'],
                'n_input_tokens':  n_input,
                'n_generated_tokens': len(generated),
                'n_think_tokens':  n_think,
                'n_answer_tokens': n_answer,
                'total_latency_ms': latency_ms,
                'truncated':   truncated,
                'think_closed': think_closed,
                'parse_status': parse_status,
                'prediction':  prediction,
                'full_think_char_len': len(think_content),
                'answer_text_preview': answer_text[:300],
                'max_new_tokens': MAX_NEW_TOKENS,
                'seed': SEED,
            }
            out_f.write(json.dumps(trial) + '\n')
            out_f.flush()

            latency_history.append(latency_ms)
            status = "TRUNC" if truncated else f"ok({n_think}tok)"
            print(f"[{idx+1}/{len(manifest)}] {sign['crop']}  n_gt={sign['n_gt']}  "
                  f"gen={len(generated)}  think={n_think}  trunc={truncated}  closed={think_closed}  "
                  f"lat={latency_ms/1000:.1f}s  {status}", flush=True)

            # runtime projection after 5 signs
            if len(latency_history) == 5:
                mean_ms    = sum(latency_history) / len(latency_history)
                remaining  = len(manifest) - len(latency_history)
                projected_h = (mean_ms * remaining) / 3_600_000
                print(f"\n=== RUNTIME PROJECTION (after 5 signs) ===")
                print(f"Mean latency so far: {mean_ms/1000:.1f}s/sign")
                print(f"Remaining: {remaining} signs")
                print(f"Projected total remaining: {projected_h:.1f}h")
                total_h = (mean_ms * len(manifest)) / 3_600_000
                print(f"Projected total run: {total_h:.1f}h")
                if projected_h > BUDGET_STOP_HOURS:
                    print(f"STOPPING: projected remaining time {projected_h:.1f}h > {BUDGET_STOP_HOURS}h limit.")
                    break
                print(f"Within {BUDGET_STOP_HOURS}h budget. Continuing.")
                print("==========================================\n", flush=True)

        except Exception as e:
            trial = {
                'crop_name': sign['crop'], 'imagePath': sign['imagePath'],
                'objectID': sign['objectID'], 'n_gt': sign['n_gt'],
                'error': str(e), 'truncated': False, 'think_closed': False,
                'max_new_tokens': MAX_NEW_TOKENS, 'seed': SEED,
            }
            out_f.write(json.dumps(trial) + '\n')
            out_f.flush()
            print(f"[{idx+1}/{len(manifest)}] ERROR: {sign['crop']}  {e}", flush=True)

    out_f.close()
    print(f"\nDone. Trials written to {TRIALS_PATH}")


if __name__ == "__main__":
    main()
