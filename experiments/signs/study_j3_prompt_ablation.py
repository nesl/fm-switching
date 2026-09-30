"""
StudyJ3 — Prompt ablation on SiGNgapore2D non-terminators.

Tests whether the 20% non-termination asymptote (StudyJ2) is prompt-induced or a
property of the task+model. Three arms on 8 cap-hit signs + 4 control completers.

Arms:
  ORIGINAL-SEED123: paper prompt verbatim, seed=123 (seed-stability check)
  SIMPLIFIED:       reduced prompt without secondary constraint clauses, seed=42
  BUDGET-AWARE:     paper prompt + explicit token-budget instruction, seed=42

Writes:
  results/signs/study_j3/study_j3_trials.jsonl
"""
import sys, json, os, time, random, ast, re, argparse, types
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

TRIALS_PATH   = "results/signs/study_j3/study_j3_trials.jsonl"

MAX_NEW_TOKENS = 24576
DIRECTIONS     = ['left', 'right', 'straight', 'straight-right', 'straight-left', 'locational']
BUDGET_STOP_HOURS = 12.0

GEN_KWARGS = dict(
    do_sample=True, temperature=0.6, top_p=0.95, top_k=20, min_p=0.0,
    max_new_tokens=MAX_NEW_TOKENS,
)

# 8 cap-hit signs from StudyJ2 (all non-terminators at 24576 tokens)
CAP_HIT_CROPS = [
    'IMG_6416_frame_0013_0.jpg',  # n_gt=3, mid
    'IMG_6546_frame_0019_1.jpg',  # n_gt=4, mid
    'IMG_6617_frame_0015_0.jpg',  # n_gt=5, mid
    'IMG_6548_frame_0019_1.jpg',  # n_gt=4, mid
    'IMG_6623_frame_0015_0.jpg',  # n_gt=7, high
    'IMG_6411_frame_0014_0.jpg',  # n_gt=3, mid
    'IMG_0037_frame_0014_0.jpg',  # n_gt=7, high
    'IMG_0068_frame_0007_0.jpg',  # n_gt=7, high
]

# 4 control completers from StudyJ2 manifest (seed=42 sample across bins)
CONTROL_CROPS = [
    'IMG_6599_frame_0016_0.jpg',  # n_gt=8, high
    'IMG_6413_frame_0022_0.jpg',  # n_gt=4, mid
    'IMG_6538_frame_0028_0.jpg',  # n_gt=1, low
    'IMG_6451_frame_0014_0.jpg',  # n_gt=2, low
]

ALL_CROPS = CAP_HIT_CROPS + CONTROL_CROPS  # 12 signs

ARMS = [
    {'name': 'ORIGINAL-SEED123', 'prompt_type': 'original', 'seed': 123},
    {'name': 'SIMPLIFIED',       'prompt_type': 'simplified', 'seed': 42},
    {'name': 'BUDGET-AWARE',     'prompt_type': 'budget_aware', 'seed': 42},
]

# ---------------------------------------------------------------------------
# Prompts — all quoted verbatim in the report
# ---------------------------------------------------------------------------

def make_prompts():
    raw = open(PROMPT_PATH).read()
    symbols = [l.strip() for l in open(SYMBOLS_PATH) if l.strip()]
    sym_str = ", ".join(symbols[:10])

    original = (raw
        .replace("GT_SYMBOL_LIST", sym_str)
        .replace("REPLACE_DIRECTION_LIST", str(DIRECTIONS)))

    # SIMPLIFIED: removes the three secondary constraint clauses.
    # Removed clauses (verbatim from original):
    #   "If a location is being represented as symbol and text both, then mention
    #    that in both 's' and 't'. For example: if you see toilet symbol as well as
    #    'TOILET' text written then add 'TOILET' to 't' and 's' both."
    #   "ONLY if there are multiple directions for a location then output all detected
    #    direction as a list. For example : 'TOILET' : ['left', 'right']  Otherwise
    #    the direction should be string. For example: 'HOSPITAL': 'left'"
    #   "The value of 's' or 't' can be empty dictionary if there are no symbol
    #    detections or no text based location names in the image."
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

    budget_suffix = ("\n\nIMPORTANT: You have a limited token budget. "
                     "Do not re-check constraints after reasoning. "
                     "Once you have identified all locations and directions, "
                     "immediately write your final JSON answer.")
    budget_aware = original + budget_suffix

    return original, simplified, budget_aware


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
                done.add((t['crop_name'], t['arm']))
            except Exception:
                pass
    return done


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Print plan and exit')
    args = parser.parse_args()

    original_prompt, simplified_prompt, budget_aware_prompt = make_prompts()
    prompt_map = {
        'original':     original_prompt,
        'simplified':   simplified_prompt,
        'budget_aware': budget_aware_prompt,
    }

    gt_map = load_gt_map()

    # build run list: interleave controls and cap-hits to get early projection
    # order: 2 controls first (fast), then cap-hits, cycling through arms
    runs = []
    for arm in ARMS:
        for crop in CONTROL_CROPS + CAP_HIT_CROPS:
            info = gt_map.get(crop)
            if info is None:
                print(f"WARNING: {crop} not in gt_map — skipping")
                continue
            role = 'control' if crop in CONTROL_CROPS else 'cap_hit'
            runs.append({'crop': crop, 'arm': arm['name'], 'prompt_type': arm['prompt_type'],
                         'seed': arm['seed'], 'role': role, 'n_gt': info['n_gt']})

    print(f"Total planned runs: {len(runs)}")
    for arm in ARMS:
        n = sum(1 for r in runs if r['arm'] == arm['name'])
        print(f"  {arm['name']}: {n} runs")

    if args.dry_run:
        print("--dry-run: exiting.")
        return

    os.makedirs(os.path.dirname(TRIALS_PATH), exist_ok=True)
    done = already_done(TRIALS_PATH)
    print(f"Already done: {len(done)}/{len(runs)}")

    print("Loading model...", flush=True)
    model     = Qwen3VLForConditionalGeneration.from_pretrained(
        THINKING_PATH, torch_dtype=torch.bfloat16, device_map=DEVICE)
    model.eval()
    processor = AutoProcessor.from_pretrained(THINKING_PATH)

    hf_cache     = {}
    out_f        = open(TRIALS_PATH, 'a')
    lat_history  = []
    run_idx      = 0

    for run in runs:
        key = (run['crop'], run['arm'])
        if key in done:
            print(f"[SKIP] {run['crop']}  arm={run['arm']}", flush=True)
            continue

        run_idx += 1
        info   = gt_map[run['crop']]
        prompt = prompt_map[run['prompt_type']]

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
            generated  = output_ids[0][n_input:]
            lat_ms     = (time.time() - t0) * 1000

            full_output = processor.decode(generated, skip_special_tokens=False)
            truncated   = len(generated) >= MAX_NEW_TOKENS

            think_content, answer_text, n_think, n_answer, think_closed = \
                extract_think_and_answer(full_output, processor)

            prediction, parse_status = parse_prediction(answer_text)

            # last 500 tokens of think for non-terminators
            last_500 = ""
            if truncated:
                last_500_ids = generated[-500:]
                last_500 = processor.decode(last_500_ids, skip_special_tokens=False)

            trial = {
                'arm': run['arm'], 'seed': run['seed'], 'role': run['role'],
                'crop_name': run['crop'], 'imagePath': info['imagePath'],
                'objectID': info['objectID'], 'n_gt': info['n_gt'],
                'n_input_tokens': n_input, 'n_generated_tokens': len(generated),
                'n_think_tokens': n_think, 'n_answer_tokens': n_answer,
                'total_latency_ms': lat_ms,
                'truncated': truncated, 'think_closed': think_closed,
                'parse_status': parse_status, 'prediction': prediction,
                'prompt_type': run['prompt_type'],
                'last_500_tokens': last_500 if truncated else "",
                'answer_text_preview': answer_text[:300],
                'max_new_tokens': MAX_NEW_TOKENS,
            }
            out_f.write(json.dumps(trial) + '\n')
            out_f.flush()

            lat_history.append(lat_ms)
            status = "TRUNC" if truncated else f"ok({n_think}tok)"
            print(f"[{run_idx}] arm={run['arm']}  {run['crop']}  n_gt={run['n_gt']}  "
                  f"role={run['role']}  gen={len(generated)}  trunc={truncated}  "
                  f"closed={think_closed}  lat={lat_ms/1000:.1f}s  {status}", flush=True)

            # projection after 4 runs
            if len(lat_history) == 4:
                mean_ms   = sum(lat_history) / len(lat_history)
                remaining = len(runs) - len(done) - len(lat_history)
                proj_h    = (mean_ms * remaining) / 3_600_000
                total_h   = (mean_ms * (len(runs) - len(done))) / 3_600_000
                print(f"\n=== RUNTIME PROJECTION (after 4 runs) ===")
                print(f"Mean latency: {mean_ms/1000:.1f}s  Remaining: {remaining}  Projected: {proj_h:.1f}h (total {total_h:.1f}h)")
                if proj_h > BUDGET_STOP_HOURS:
                    print(f"STOPPING: projected {proj_h:.1f}h > {BUDGET_STOP_HOURS}h limit.")
                    break
                print(f"Within {BUDGET_STOP_HOURS}h. Continuing.")
                print("==========================================\n", flush=True)

        except Exception as e:
            trial = {'arm': run['arm'], 'seed': run['seed'], 'role': run['role'],
                     'crop_name': run['crop'], 'n_gt': info['n_gt'],
                     'error': str(e), 'truncated': False, 'think_closed': False,
                     'max_new_tokens': MAX_NEW_TOKENS, 'prompt_type': run['prompt_type']}
            out_f.write(json.dumps(trial) + '\n')
            out_f.flush()
            print(f"[{run_idx}] ERROR arm={run['arm']}  {run['crop']}  {e}", flush=True)

    out_f.close()
    print(f"\nDone. Trials written to {TRIALS_PATH}")


if __name__ == "__main__":
    main()
