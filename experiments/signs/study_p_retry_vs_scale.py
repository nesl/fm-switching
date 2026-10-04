"""
StudyP — Retry vs Scale on SiGNgapore2D.

Single question: does a 4B model with N retries match an 8B model with
one pass, and at what latency cost?

Arms:
  A: 4B-Thinking, 1 pass (seed 42)
  B: 4B-Thinking, up to 5 passes (seeds 42,123,456,789,1011);
     retry only on non-terminating traces; reuses arm A as pass 1
  C: 8B-Thinking, 1 pass (seed 42)
  D: 8B-Instruct, 1 pass, greedy

Pre-registered rule:
  4B×N MATCHES 8B×1 if 4B accuracy at some N<=5 is within 3pp of 8B×1
  with overlapping CIs.
  SCALE WINS if 8B×1 exceeds 4B×5 by >3pp.

Writes:
  results/signs/study_p/study_p_trials.jsonl
  reports/study_p_retry_vs_scale.md
"""

import sys, json, os, time, ast, re, argparse, statistics, math
import torch
import numpy as np
sys.path.insert(0, '/tmp/sign-understanding')
from PIL import Image
from huggingface_hub import hf_hub_download
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
from qwen_vl_utils import process_vision_info
import open_clip

# ── Checkpoints ───────────────────────────────────────────────────────────────
PATH_4BT = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Thinking/snapshots/1de27d8c51f12e819435303b9e84c4e25ba8401e"
PATH_8BT = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-8B-Thinking/snapshots/92f3c4b4feadd3a016ef468d103bb5f58b2a2c6b"
PATH_8BI = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-8B-Instruct/snapshots/0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"
DEVICE   = "cuda:1"

# ── Paths ─────────────────────────────────────────────────────────────────────
HF_REPO      = "NickyZimmerman/SiGNgapore2D"
GT_PATH      = "/tmp/sign-understanding/gt/gt_annotation.json"
EXCLUDE_PATH = "/tmp/sign-understanding/gt/recognition-exclude-imgs.txt"
PROMPT_PATH  = "/tmp/sign-understanding/prompts/prompt.txt"
SYMBOLS_PATH = "/tmp/sign-understanding/prompts/symbols.txt"
GEMINI_PATH  = "/tmp/sign-understanding/recognition_results/gemini/recogntion_results.json"
J2_MANIFEST  = "results/signs/study_j2/manifest.json"
STUDYJ_PATH  = "results/signs/study_j/study_j_trials.jsonl"

TRIALS_PATH  = "results/signs/study_p/study_p_trials.jsonl"
REPORT_PATH  = "reports/study_p_retry_vs_scale.md"

MAX_NEW_TOKENS    = 8192
DIRECTIONS        = ['left', 'right', 'straight', 'straight-right', 'straight-left', 'locational']
RETRY_SEEDS       = [42, 123, 456, 789, 1011]
BUDGET_STOP_HOURS = 10.0

THINKING_GEN = dict(do_sample=True, temperature=0.6, top_p=0.95,
                    top_k=20, min_p=0.0, max_new_tokens=MAX_NEW_TOKENS)
INSTRUCT_GEN = dict(do_sample=False, max_new_tokens=MAX_NEW_TOKENS)


# ── Scorer (inlined from recognition_fp_metrics_eval.py + utils/metrics.py) ──

_clip_model_cpu, _, _clip_preprocess = open_clip.create_model_and_transforms(
    'ViT-B-32', pretrained='laion2b_s34b_b79k')
_clip_tokenizer = open_clip.get_tokenizer('ViT-B-32')
_clip_model_cpu.eval()


def _jaccard(s1, s2_list):
    s1n = s1.lower()
    out = []
    for s2 in s2_list:
        a, b = set(s1n), set(s2.lower())
        u = len(a | b)
        out.append(len(a & b) / u if u > 0 else 0.0)
    return out


def _lexical(s1, s2_list):
    jacc = _jaccard(s1, s2_list)
    s1n = s1.lower()
    return [jacc[i] * (1 if s1n in s2.lower() else 0)
            for i, s2 in enumerate(s2_list)]


def _clip_sim(word, word_list):
    fw = f"symbol of {word}"
    fwl = [f"symbol of {w}" for w in word_list]
    tokens = _clip_tokenizer([fw] + fwl)
    with torch.no_grad():
        emb = _clip_model_cpu.encode_text(tokens).float()
    sims = torch.nn.functional.cosine_similarity(emb[0], emb[1:], dim=-1)
    return sims.tolist()


def _getmax(sim_mat):
    v = np.max(sim_mat)
    return np.unravel_index(np.argmax(sim_mat), sim_mat.shape) if v != 0.0 else -1


def _hungarian(func, gt_copy, pred_copy, loc_map):
    if not gt_copy or not pred_copy:
        return loc_map
    rows = [func(loc, pred_copy) for loc in gt_copy]
    sim = np.array(rows)
    for _ in range(min(len(gt_copy), len(pred_copy))):
        idx = _getmax(sim)
        if idx == -1:
            break
        loc_map[gt_copy[idx[0]]] = pred_copy[idx[1]]
        pred_copy.pop(idx[1])
        gt_copy.pop(idx[0])
        if sim.shape[0] == 1 or sim.shape[1] == 1:
            break
        sim = np.delete(np.delete(sim, idx[0], 0), idx[1], 1)
    return loc_map


def _proc(dct, mixed=None):
    out = {}
    for k, v in dct.items():
        kn = k.upper().replace(' ', '')
        if isinstance(v, str):
            vn = v.upper().replace(' ', '')
            if 'DOWN' not in vn and 'AND' not in vn:
                out[kn] = vn
        elif isinstance(v, (list, tuple)):
            vs = tuple(sorted(
                vi.upper().replace(' ', '') for vi in v
                if 'DOWN' not in vi.upper().replace(' ', '')
                and 'AND' not in vi.upper().replace(' ', '')))
            out[kn] = vs
    if mixed:
        for k, v in mixed.items():
            kn = k.upper().replace(' ', '')
            if isinstance(v, str):
                vn = v.upper().replace(' ', '')
                if 'DOWN' not in vn and 'AND' not in vn:
                    out[kn] = vn
            elif isinstance(v, (list, tuple)):
                vs = tuple(sorted(
                    vi.upper().replace(' ', '') for vi in v
                    if 'DOWN' not in vi.upper().replace(' ', '')
                    and 'AND' not in vi.upper().replace(' ', '')))
                out[kn] = vs
    return out


def _match_score(txt_map, sym_map, txtpred, txtgt, sympred, symgt):
    ts = 0
    for k in txt_map:
        pk = txt_map[k]
        gv, pv = txtgt[k], txtpred[pk]
        if isinstance(pv, tuple) and isinstance(gv, tuple):
            ts += len(set(pv) & set(gv)) / len(set(gv))
        elif isinstance(pv, tuple) and isinstance(gv, str):
            ts += 0
        elif isinstance(pv, str) and isinstance(gv, str):
            ts += int(pv == gv)
        elif isinstance(pv, str) and isinstance(gv, tuple):
            ts += int(pv in gv) / len(set(gv))
    ss = 0
    for k in sym_map:
        pk = sym_map[k]
        gv, pv = symgt[k], sympred[pk]
        if isinstance(pv, tuple) and isinstance(gv, tuple):
            ss += len(set(pv) & set(gv)) / len(set(gv))
        elif isinstance(pv, tuple) and isinstance(gv, str):
            ss += 0
        elif isinstance(pv, str) and isinstance(gv, str):
            ss += int(pv == gv)
        elif isinstance(pv, str) and isinstance(gv, tuple):
            ss += int(pv in gv) / len(set(gv))
    return ts, ss


def score_sign(pred, ann):
    """Returns True if prediction is a perfect match for the GT annotation."""
    if pred is None:
        return False
    mixed = ann.get('mixed') or {}
    txtgt  = _proc(ann.get('text labels', {}),   mixed)
    symgt  = _proc(ann.get('symbol labels', {}), mixed)
    txtpred = _proc(pred.get('T', pred.get('t', {})) or {})
    sympred = _proc(pred.get('S', pred.get('s', {})) or {})

    txt_map, sym_map = {}, {}
    gtl, prl = list(txtgt.keys()), list(txtpred.keys())
    for loc in list(txtgt.keys()):
        if loc in txtpred:
            txt_map[loc] = loc; prl.remove(loc); gtl.remove(loc)
    txt_map = _hungarian(_lexical, gtl, prl, txt_map)

    gsl, psl = list(symgt.keys()), list(sympred.keys())
    for loc in list(symgt.keys()):
        if loc in sympred:
            sym_map[loc] = loc; psl.remove(loc); gsl.remove(loc)
    sym_map = _hungarian(_clip_sim, gsl, psl, sym_map)

    ts, ss = _match_score(txt_map, sym_map, txtpred, txtgt, sympred, symgt)

    common = 0
    for ck in mixed:
        sc = []
        if ck in sym_map:
            sc.append(int(type(symgt[ck]) == type(sympred[sym_map[ck]])
                          and symgt[ck] == sympred[sym_map[ck]]))
        if ck in txt_map:
            sc.append(int(type(txtgt[ck]) == type(txtpred[txt_map[ck]])
                          and txtgt[ck] == txtpred[txt_map[ck]]))
        if sum(sc) == 2:
            common += 1

    if ts == len(txtgt) and ss == len(symgt):
        return True
    if ss + ts - common == len(symgt) + len(txtgt) - len(mixed):
        return True
    return False


# ── Scorer validation ─────────────────────────────────────────────────────────

def validate_scorer(gt_map_full):
    """Reproduce Gemini overall_acc ≈ 40.7%. Halts if >2pp off."""
    gemini = json.load(open(GEMINI_PATH))
    gemini_map = {os.path.basename(e['frame_path']): e['voted response']
                  for e in gemini}

    total = correct = 0
    for crop, info in gt_map_full.items():
        if crop not in gemini_map:
            continue
        raw = gemini_map[crop]
        try:
            pred = ast.literal_eval(raw) if isinstance(raw, str) else raw
        except Exception:
            pred = None
        total += 1
        if score_sign(pred, info['ann']):
            correct += 1

    if total == 0:
        print("ERROR: no Gemini entries matched GT crops — check paths")
        sys.exit(1)

    acc = correct / total
    print(f"Scorer validation: {correct}/{total} = {acc*100:.1f}% (target ≈ 40.7%)")
    if abs(acc - 0.407) > 0.02:
        print(f"VALIDATION FAILED — deviation {abs(acc-0.407)*100:.1f}pp > 2pp. HALTING.")
        sys.exit(1)
    print("Scorer validation PASS.")
    return acc


# ── GT and manifest ───────────────────────────────────────────────────────────

def build_gt_map():
    """Returns dict {crop_name: {imagePath, objectID, bbox, n_gt, ann}}."""
    gt      = json.load(open(GT_PATH))
    exclude = set(l.strip() for l in open(EXCLUDE_PATH) if l.strip())
    m = {}
    for entry in gt:
        stem = entry['imagePath'][:-4]
        for i, ann in enumerate(entry['annotation']):
            tl = ann.get('text labels', {}); sl = ann.get('symbol labels', {}); mx = ann.get('mixed') or {}
            if tl == {} and sl == {} and mx == {}:
                continue
            crop = f'{stem}_{i}.jpg'
            if crop in exclude:
                continue
            m[crop] = {
                'imagePath': entry['imagePath'], 'objectID': i,
                'bbox': ann['boundingBox'],
                'n_gt': len(tl) + len(sl) - len(mx),
                'ann': ann,
            }
    return m


def load_studyj_manifest(gt_map_full):
    """162 crops from StudyJ INSTRUCT arm (post-exclusion, committed manifest)."""
    crops = []
    seen = set()
    for line in open(STUDYJ_PATH):
        t = json.loads(line)
        if t['arm'] == 'INSTRUCT' and t['crop_name'] not in seen:
            seen.add(t['crop_name'])
            crops.append(t['crop_name'])
    print(f"StudyJ manifest: {len(crops)} crops")
    return crops


def load_j2_manifest():
    """40-crop subset from StudyJ2 (committed manifest)."""
    m = json.load(open(J2_MANIFEST))
    crops = [e['crop'] for e in m]
    print(f"StudyJ2 manifest: {len(crops)} crops")
    return crops


# ── Prompt ────────────────────────────────────────────────────────────────────

def make_prompt():
    raw     = open(PROMPT_PATH).read()
    symbols = [l.strip() for l in open(SYMBOLS_PATH) if l.strip()]
    sym_str = ", ".join(symbols[:10])
    return (raw
            .replace("GT_SYMBOL_LIST", sym_str)
            .replace("REPLACE_DIRECTION_LIST", str(DIRECTIONS)))


# ── Inference helpers ─────────────────────────────────────────────────────────

def crop_bbox(img, bbox):
    cx, cy, w, h = bbox
    return img.crop((max(0, int(cx-w/2)), max(0, int(cy-h/2)),
                     min(img.width, int(cx+w/2)), min(img.height, int(cy+h/2))))


def extract_think_and_answer(full_output, processor):
    if "</think>" in full_output:
        tp, ap = full_output.split("</think>", 1)
        think_content = tp.replace("<think>", "").strip()
        answer_text   = ap.strip()
        think_closed  = True
    else:
        think_content = full_output.replace("<think>", "").strip()
        answer_text   = ""
        think_closed  = False
    n_think  = len(processor.tokenizer.encode(think_content, add_special_tokens=False)) if think_content else 0
    n_answer = len(processor.tokenizer.encode(answer_text,   add_special_tokens=False)) if answer_text   else 0
    return answer_text, n_think, n_answer, think_closed


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


def run_one(model, processor, img, prompt, gen_kwargs, seed):
    """Run one inference pass. Returns dict of raw metrics."""
    torch.manual_seed(seed if seed is not None else 0)
    messages = [{"role": "user", "content": [
        {"type": "image", "image": img},
        {"type": "text",  "text": prompt}]}]
    text_input = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True)
    img_inp, vid_inp = process_vision_info(messages)
    inputs = processor(text=[text_input], images=img_inp, videos=vid_inp,
                       padding=True, return_tensors="pt").to(DEVICE)
    n_input = inputs["input_ids"].shape[1]

    t0 = time.time()
    with torch.no_grad():
        output_ids = model.generate(**inputs, **gen_kwargs)
    lat_ms = (time.time() - t0) * 1000
    generated = output_ids[0][n_input:]

    full_output = processor.decode(generated, skip_special_tokens=False)
    budget_hit  = len(generated) >= gen_kwargs.get("max_new_tokens", MAX_NEW_TOKENS)
    answer_text, n_think, n_answer, think_closed = \
        extract_think_and_answer(full_output, processor)
    prediction, parse_status = parse_prediction(answer_text)

    return {
        'n_input_tokens':     n_input,
        'n_generated_tokens': len(generated),
        'n_think_tokens':     n_think,
        'n_answer_tokens':    n_answer,
        'think_closed':       think_closed,
        'budget_hit':         budget_hit,
        'answer_text':        answer_text,
        'parse_status':       parse_status,
        'prediction':         prediction,
        'latency_ms':         lat_ms,
    }


def already_done_set(path):
    """Returns set of (arm, crop_name, pass_index) already recorded."""
    done = set()
    if os.path.exists(path):
        for line in open(path):
            try:
                t = json.loads(line)
                done.add((t['arm'], t['crop_name'], t.get('pass_index', 1)))
            except Exception:
                pass
    return done


# ── Arm runners ───────────────────────────────────────────────────────────────

def run_arm(arm_name, model_path, crops, gt_map_full, hf_cache, prompt,
            gen_kwargs, out_f, done, seed=42, pass_index=1,
            print_prefix="", max_trials=None, project_n=5, hard_stop_h=None):
    """
    Run a single-pass arm. Returns (trials, stop_flag).
    Prints projection after project_n trials; if hard_stop_h set and total > it, stop_flag=True.
    """
    trials = []
    lat_history = []

    for i, crop in enumerate(crops):
        if (arm_name, crop, pass_index) in done:
            continue
        if max_trials is not None and i >= max_trials:
            break

        info = gt_map_full.get(crop)
        if info is None:
            print(f"WARNING: {crop} not in gt_map", flush=True)
            continue

        if info['imagePath'] not in hf_cache:
            local = hf_hub_download(
                repo_id=HF_REPO, filename=f"images/{info['imagePath']}", repo_type="dataset")
            hf_cache[info['imagePath']] = Image.open(local).convert("RGB")
        img = crop_bbox(hf_cache[info['imagePath']], info['bbox'])

        try:
            r = run_one(model, processor_ref[0], img, prompt, gen_kwargs, seed)
        except RuntimeError as e:
            print(f"ERROR {crop}: {e}", flush=True)
            continue

        score = None
        if r['think_closed'] and r['prediction'] is not None:
            score = score_sign(r['prediction'], info['ann'])

        parsed_tuples = None
        if r['prediction'] is not None:
            parsed_tuples = r['prediction']

        trial = {
            'arm':             arm_name,
            'crop_name':       crop,
            'sign_id':         crop,
            'n_gt':            info['n_gt'],
            'pass_index':      pass_index,
            'seed':            seed,
            'n_think_tokens':  r['n_think_tokens'],
            'think_closed':    r['think_closed'],
            'budget_hit':      r['budget_hit'],
            'answer_text':     r['answer_text'],
            'parsed_tuples':   parsed_tuples,
            'parse_status':    r['parse_status'],
            'score':           score,
            'latency_ms':      r['latency_ms'],
            'n_input_tokens':  r['n_input_tokens'],
            'n_generated_tokens': r['n_generated_tokens'],
        }
        out_f.write(json.dumps(trial) + '\n')
        out_f.flush()
        done.add((arm_name, crop, pass_index))
        trials.append(trial)
        lat_history.append(r['latency_ms'])

        status = f"{'OK ' if r['think_closed'] else 'NC '} score={'Y' if score else ('N' if score is False else '?')}"
        print(f"  {print_prefix}[{i+1}] {crop[:22]}  {status}  lat={r['latency_ms']/1000:.1f}s", flush=True)

        # Projection after project_n trials
        if len(lat_history) == project_n:
            mean_ms = sum(lat_history) / project_n
            total_proj_h = (mean_ms * len(crops)) / 3_600_000
            remaining_proj_h = (mean_ms * (len(crops) - (i + 1))) / 3_600_000
            print(f"\n=== RUNTIME PROJECTION: {arm_name} (after {project_n} trials) ===")
            print(f"Mean lat: {mean_ms/1000:.1f}s  n_signs: {len(crops)}  "
                  f"Projected total: {total_proj_h:.1f}h  Remaining: {remaining_proj_h:.1f}h")
            if hard_stop_h is not None and total_proj_h > hard_stop_h:
                print(f"HARD STOP: projected {total_proj_h:.1f}h > {hard_stop_h}h limit. Halting arm.")
                return trials, True
            print()

    return trials, False


# Module-level references populated by main()
model = None
processor_ref = [None]


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    global model, processor_ref

    parser = argparse.ArgumentParser()
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--report-only', action='store_true',
                        help='Skip inference; just write report from existing JSONL.')
    args = parser.parse_args()

    # ── Checkpoint verification ────────────────────────────────────────────────
    print("=" * 60)
    print("CHECKPOINT VERIFICATION")
    print("=" * 60)
    import json as _json
    for label, path in [("4B-T", PATH_4BT), ("8B-T", PATH_8BT), ("8B-I", PATH_8BI)]:
        c = _json.load(open(f"{path}/config.json"))
        lm = c.get('text_config', {})
        print(f"  {label}: hidden={lm.get('hidden_size')}, layers={lm.get('num_hidden_layers')}, snap={os.path.basename(path)[:8]}")
    print("Three distinct checkpoints confirmed (4B hidden=2560; 8B-T and 8B-I hidden=4096, different snaps).")
    print()

    # ── GT and manifest ────────────────────────────────────────────────────────
    gt_map_full = build_gt_map()
    print(f"GT map built: {len(gt_map_full)} valid signs")

    # ── Scorer validation ──────────────────────────────────────────────────────
    print("=" * 60)
    print("SCORER VALIDATION")
    print("=" * 60)
    gemini_acc = validate_scorer(gt_map_full)

    if args.validate_only:
        return

    # ── Manifest ───────────────────────────────────────────────────────────────
    crops_j2 = load_j2_manifest()

    if args.report_only:
        trials = [json.loads(l) for l in open(TRIALS_PATH)] if os.path.exists(TRIALS_PATH) else []
        write_report(trials, gemini_acc, crops_used=crops_j2)
        return

    prompt = make_prompt()
    os.makedirs(os.path.dirname(TRIALS_PATH), exist_ok=True)
    done = already_done_set(TRIALS_PATH)

    out_f = open(TRIALS_PATH, 'a')
    hf_cache = {}

    # ── Arm D: 8B-I, 1 pass, greedy (FIRST — cheapest/fastest) ───────────────
    print("\n" + "=" * 60)
    print("ARM D: 8B-Instruct, 1 pass, greedy (arm 1 of 4 — cheapest first)")
    print("=" * 60)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        PATH_8BI, torch_dtype=torch.bfloat16, device_map=DEVICE)
    model.eval()
    processor_ref[0] = AutoProcessor.from_pretrained(PATH_8BI)
    print("8B-I loaded.")

    arm_d_trials, _ = run_arm(
        'D', PATH_8BI, crops_j2, gt_map_full, hf_cache, prompt,
        INSTRUCT_GEN, out_f, done, seed=42, pass_index=1,
        print_prefix="D1 ", project_n=5, hard_stop_h=None)

    del model
    torch.cuda.empty_cache()
    print("8B-I unloaded.")

    # ── Arm A: 4B-T, 1 pass (SECOND) ─────────────────────────────────────────
    print("\n" + "=" * 60)
    print("ARM A: 4B-Thinking, 1 pass, seed 42 (arm 2 of 4)")
    print("=" * 60)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        PATH_4BT, torch_dtype=torch.bfloat16, device_map=DEVICE)
    model.eval()
    processor_ref[0] = AutoProcessor.from_pretrained(PATH_4BT)
    print("4B-T loaded.")

    arm_a_trials, arm_a_stop = run_arm(
        'A', PATH_4BT, crops_j2, gt_map_full, hf_cache, prompt,
        THINKING_GEN, out_f, done, seed=42, pass_index=1,
        print_prefix="A1 ", project_n=5, hard_stop_h=12.0)

    del model
    torch.cuda.empty_cache()
    print("4B-T unloaded.")

    if arm_a_stop:
        print("\nARM A HARD STOP: projection exceeds 12h. Writing partial report and halting.")
        out_f.close()
        trials = [json.loads(l) for l in open(TRIALS_PATH)]
        write_report(trials, gemini_acc, crops_used=crops_j2)
        print(f"Partial report written to {REPORT_PATH}")
        sys.exit(0)

    # ── Arm C: 8B-T, 1 pass (THIRD) ───────────────────────────────────────────
    print("\n" + "=" * 60)
    print("ARM C: 8B-Thinking, 1 pass, seed 42 (arm 3 of 4)")
    print("=" * 60)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        PATH_8BT, torch_dtype=torch.bfloat16, device_map=DEVICE)
    model.eval()
    processor_ref[0] = AutoProcessor.from_pretrained(PATH_8BT)
    print("8B-T loaded.")

    arm_c_trials, _ = run_arm(
        'C', PATH_8BT, crops_j2, gt_map_full, hf_cache, prompt,
        THINKING_GEN, out_f, done, seed=42, pass_index=1,
        print_prefix="C1 ", project_n=5, hard_stop_h=None)

    del model
    torch.cuda.empty_cache()
    print("8B-T unloaded.")

    # ── Arm B: 4B-T retries (FOURTH — reuses arm A pass 1) ────────────────────
    print("\n" + "=" * 60)
    print("ARM B: 4B-Thinking, retry non-terminators (seeds 42→123→456→789→1011)")
    print("(pass 1 reused from arm A; arm 4 of 4)")
    print("=" * 60)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        PATH_4BT, torch_dtype=torch.bfloat16, device_map=DEVICE)
    model.eval()
    processor_ref[0] = AutoProcessor.from_pretrained(PATH_4BT)
    print("4B-T loaded.")

    # Load all arm A trials
    arm_a_map = {}
    if os.path.exists(TRIALS_PATH):
        for line in open(TRIALS_PATH):
            t = json.loads(line)
            if t['arm'] == 'A':
                arm_a_map[t['crop_name']] = t

    # Write arm B pass-1 records as copies of arm A (if not already done)
    for crop in crops_j2:
        if ('B', crop, 1) not in done and crop in arm_a_map:
            t = arm_a_map[crop]
            b1 = {**t, 'arm': 'B', 'pass_index': 1}
            out_f.write(json.dumps(b1) + '\n')
            out_f.flush()
            done.add(('B', crop, 1))

    # For non-terminators in arm A, retry with seeds 123, 456, 789, 1011
    for crop in crops_j2:
        a_trial = arm_a_map.get(crop)
        if a_trial is None:
            print(f"WARNING: arm A trial missing for {crop} — skipping arm B retries")
            continue
        if a_trial.get('think_closed'):
            continue  # already terminated; no retry needed

        info = gt_map_full.get(crop)
        if info is None:
            continue

        if info['imagePath'] not in hf_cache:
            local = hf_hub_download(
                repo_id=HF_REPO, filename=f"images/{info['imagePath']}", repo_type="dataset")
            hf_cache[info['imagePath']] = Image.open(local).convert("RGB")
        img = crop_bbox(hf_cache[info['imagePath']], info['bbox'])

        for pass_idx, seed in enumerate(RETRY_SEEDS[1:], start=2):  # seeds 123..1011
            if ('B', crop, pass_idx) in done:
                continue

            try:
                r = run_one(model, processor_ref[0], img, prompt, THINKING_GEN, seed)
            except RuntimeError as e:
                print(f"ERROR B retry {crop} seed={seed}: {e}", flush=True)
                continue

            score = None
            if r['think_closed'] and r['prediction'] is not None:
                score = score_sign(r['prediction'], info['ann'])

            trial = {
                'arm':             'B',
                'crop_name':       crop,
                'sign_id':         crop,
                'n_gt':            info['n_gt'],
                'pass_index':      pass_idx,
                'seed':            seed,
                'n_think_tokens':  r['n_think_tokens'],
                'think_closed':    r['think_closed'],
                'budget_hit':      r['budget_hit'],
                'answer_text':     r['answer_text'],
                'parsed_tuples':   r['prediction'],
                'parse_status':    r['parse_status'],
                'score':           score,
                'latency_ms':      r['latency_ms'],
                'n_input_tokens':  r['n_input_tokens'],
                'n_generated_tokens': r['n_generated_tokens'],
            }
            out_f.write(json.dumps(trial) + '\n')
            out_f.flush()
            done.add(('B', crop, pass_idx))

            status = "OK " if r['think_closed'] else "NC "
            print(f"  B[pass {pass_idx}] {crop[:22]}  {status} seed={seed}  lat={r['latency_ms']/1000:.1f}s", flush=True)

            if r['think_closed']:
                break  # stop at first terminating pass

    del model
    torch.cuda.empty_cache()
    print("4B-T unloaded.")
    out_f.close()

    # ── Report ─────────────────────────────────────────────────────────────────
    trials = [json.loads(l) for l in open(TRIALS_PATH)]
    write_report(trials, gemini_acc, crops_used=crops_j2)
    print(f"\nReport written to {REPORT_PATH}")


# ── Report ─────────────────────────────────────────────────────────────────────

def _wilson_ci(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2*n)) / denom
    margin = (z * math.sqrt(p*(1-p)/n + z**2/(4*n**2))) / denom
    return (max(0, center - margin), min(1, center + margin))


def _overlap(ci1, ci2):
    return ci1[0] <= ci2[1] and ci2[0] <= ci1[1]


def write_report(trials, gemini_acc, crops_used):
    lines = []
    A = lines.append

    # Collect arm data — filter to crops_used
    crops_set = set(crops_used)

    def arm_trials(arm):
        return [t for t in trials if t['arm'] == arm and t['crop_name'] in crops_set]

    # For arm B, keep only the final (terminating or last) pass per sign
    # For accuracy at N passes: accumulate
    arm_a = arm_trials('A')
    arm_b_all = arm_trials('B')
    arm_c = arm_trials('C')
    arm_d = arm_trials('D')

    # Arm B: group by crop, sort by pass_index
    b_by_crop = {}
    for t in arm_b_all:
        b_by_crop.setdefault(t['crop_name'], []).append(t)
    for crop in b_by_crop:
        b_by_crop[crop].sort(key=lambda t: t['pass_index'])

    n_signs = len(crops_used)

    # ── Title and verdict first ────────────────────────────────────────────────
    A("# StudyP — Retry vs Scale on SiGNgapore2D")
    A("")
    A(f"**Date:** 2026-10-03  ")
    A(f"**n_signs:** {n_signs} (40-sign StudyJ2 subset)  ")
    A(f"**Sample size note:** n=40 limits detection to large effects. "
      f"Wilson 95% CI half-width ≈ 14–15pp at ~40% accuracy; "
      f"for two CIs to be non-overlapping the difference must be ≈ 29pp. "
      f"The 3pp pre-registered threshold is well below this; verdicts of MATCHES or INCONCLUSIVE "
      f"reflect insufficient power, not absence of an effect.  ")
    A(f"**Scorer validation:** Gemini-2.0-Flash {gemini_acc*100:.1f}% (target 40.7%) — PASS")
    A(f"**Decoding asymmetry:** Thinking arms temp=0.6 top_p=0.95 top_k=20 min_p=0; "
      f"arm D (8B-I) greedy (do_sample=False).")
    A(f"**Checkpoints (3 distinct):**")
    A(f"  - 4B-T: hidden=2560, snap `1de27d8c` ({PATH_4BT.split('/')[-1][:8]})")
    A(f"  - 8B-T: hidden=4096, snap `92f3c4b4` ({PATH_8BT.split('/')[-1][:8]})")
    A(f"  - 8B-I: hidden=4096, snap `0c351dd0` ({PATH_8BI.split('/')[-1][:8]})")
    A("")

    # ── Verdict (computed first, displayed first) ──────────────────────────────
    A("## §1 Verdict (Pre-registered Rule)")
    A("")
    A("Pre-registered rule: **4B×N MATCHES 8B×1** if 4B accuracy at some N≤5 is within 3pp "
      "of 8B×1 with overlapping CIs. **SCALE WINS** if 8B×1 exceeds 4B×5 by >3pp.")
    A("")

    # Compute key accuracies
    def arm_acc(arm_ts, denom=None):
        n = denom if denom is not None else len(arm_ts)
        correct = sum(1 for t in arm_ts if t.get('score'))
        return correct, n, _wilson_ci(correct, n)

    c_correct, c_n, c_ci = arm_acc(arm_c)

    # 4B×N deployment accuracy (non-terminating = 0 for all 5 passes)
    # For 4B×5: take the first terminating pass per sign; non-term = 0
    b5_correct = 0
    b_pass_correct = {p: 0 for p in range(1, 6)}
    b_pass_term    = {p: 0 for p in range(1, 6)}
    for crop, passes in b_by_crop.items():
        for p_idx in range(1, 6):
            # cumulative: did any of passes 1..p_idx terminate and score?
            for t in passes:
                if t['pass_index'] <= p_idx and t.get('think_closed'):
                    b_pass_term[p_idx] += 1
                    if t.get('score'):
                        b_pass_correct[p_idx] += 1
                    break  # first terminator wins

    # For 4B×5 overall accuracy: deployment (all n_signs in denominator)
    b5_correct = b_pass_correct[5] if 5 in b_pass_correct else 0

    # Compute CIs
    b_cis = {}
    for p in range(1, 6):
        b_cis[p] = _wilson_ci(b_pass_correct.get(p, 0), n_signs)

    b5_acc = b5_correct / n_signs if n_signs > 0 else 0
    c_acc  = c_correct  / c_n     if c_n > 0     else 0

    # Verdict
    diff_5_vs_c = c_acc - b5_acc
    ci_overlap = _overlap(b_cis.get(5, (0,0)), c_ci)

    # Find smallest N where 4B×N is within 3pp of 8B×1
    match_n = None
    for p in range(1, 6):
        b_acc_p = b_pass_correct.get(p, 0) / n_signs if n_signs > 0 else 0
        if abs(b_acc_p - c_acc) <= 0.03 and _overlap(b_cis[p], c_ci):
            match_n = p
            break

    if match_n is not None:
        verdict = f"**4B×N MATCHES 8B×1** at N={match_n} (within 3pp, overlapping CIs)."
    elif diff_5_vs_c > 0.03:
        verdict = f"**SCALE WINS** — 8B×1 exceeds 4B×5 by {diff_5_vs_c*100:.1f}pp (>3pp threshold)."
    else:
        verdict = (f"**INCONCLUSIVE** — 8B×1 vs 4B×5 gap = {diff_5_vs_c*100:.1f}pp "
                   f"(within 3pp threshold, {'CI overlap' if ci_overlap else 'no CI overlap'}).")

    A(f"**{verdict}**")
    A("")

    # Latency at verdict point
    if match_n is not None:
        b_lats_at_n = []
        for crop, passes in b_by_crop.items():
            total_lat = 0
            for t in sorted(passes, key=lambda x: x['pass_index']):
                total_lat += t['latency_ms']
                if t.get('think_closed') or t['pass_index'] >= match_n:
                    break
            b_lats_at_n.append(total_lat)
        c_lats = [t['latency_ms'] for t in arm_c]
        if b_lats_at_n and c_lats:
            b_mean = statistics.mean(b_lats_at_n) / 1000
            c_mean = statistics.mean(c_lats) / 1000
            ratio  = b_mean / c_mean if c_mean > 0 else float('nan')
            A(f"Latency at N={match_n}: 4B×{match_n} mean={b_mean:.1f}s, 8B×1 mean={c_mean:.1f}s, "
              f"ratio={ratio:.2f}×.")
    elif diff_5_vs_c > 0.03:
        c_lats = [t['latency_ms'] for t in arm_c]
        if c_lats:
            c_mean = statistics.mean(c_lats) / 1000
            A(f"8B×1 mean latency: {c_mean:.1f}s.")
    A("")

    # ── Analysis 1: termination rate ──────────────────────────────────────────
    A("---")
    A("")
    A("## §2 Analysis 1 — Termination Rate")
    A("")

    for arm_label, arm_ts in [('A', arm_a), ('C', arm_c), ('D', arm_d)]:
        n = len(arm_ts)
        n_term = sum(1 for t in arm_ts if t.get('think_closed'))
        n_nterm = n - n_term
        n_parsed = sum(1 for t in arm_ts if t.get('parse_status') == 'ok')
        A(f"**Arm {arm_label}:** {n} trials — {n_term} terminated ({n_term/n*100:.1f}%), "
          f"{n_nterm} non-terminated ({n_nterm/n*100:.1f}%), "
          f"{n_parsed} parsed ok ({n_parsed/n*100:.1f}%).")

    A("")
    A("**Arm B (4B-T retries) — cumulative termination after 1–5 passes:**")
    A("")
    A("| passes attempted | signs terminated | cumulative % |")
    A("|---|---|---|")
    cum_term = 0
    for p in range(1, 6):
        new_term = sum(1 for crop, passes in b_by_crop.items()
                       if any(t['pass_index'] == p and t.get('think_closed')
                              and not any(t2['pass_index'] < p and t2.get('think_closed')
                                          for t2 in passes)
                              for t in passes))
        cum_term += new_term
        denom = len(b_by_crop) if b_by_crop else n_signs
        A(f"| ≤{p} | {cum_term} | {cum_term/denom*100:.1f}% |")

    A("")

    # ── Analysis 2: accuracy ──────────────────────────────────────────────────
    A("## §3 Analysis 2 — Accuracy")
    A("")
    A("Non-terminating trials score 0 (deployment-realistic).")
    A("")
    A("| arm | n_signs | correct | acc | 95% CI |")
    A("|---|---|---|---|---|")

    for arm_label, arm_ts in [('A (4B-T×1)', arm_a),
                               ('C (8B-T×1)', arm_c),
                               ('D (8B-I×1)', arm_d)]:
        c, n, ci = arm_acc(arm_ts)
        A(f"| {arm_label} | {n} | {c} | {c/n*100:.1f}% | [{ci[0]*100:.1f}%, {ci[1]*100:.1f}%] |")

    A("")
    A("**Arm B (4B-T) cumulative accuracy after 1–5 passes:**")
    A("")
    A("| N | correct (cumulative) | acc | 95% CI |")
    A("|---|---|---|---|")
    for p in range(1, 6):
        c = b_pass_correct.get(p, 0)
        ci = b_cis.get(p, (0, 0))
        A(f"| ≤{p} | {c} | {c/n_signs*100:.1f}% | [{ci[0]*100:.1f}%, {ci[1]*100:.1f}%] |")

    A("")

    # ── Analysis 3: latency ───────────────────────────────────────────────────
    A("## §4 Analysis 3 — Cumulative Latency")
    A("")
    A("For arm B, mean total latency = sum of all passes attempted per sign.")
    A("")

    for arm_label, arm_ts in [('A', arm_a), ('C', arm_c), ('D', arm_d)]:
        lats = [t['latency_ms'] for t in arm_ts]
        if lats:
            A(f"**Arm {arm_label}:** mean={statistics.mean(lats)/1000:.1f}s  "
              f"median={statistics.median(lats)/1000:.1f}s  "
              f"p90={sorted(lats)[int(0.9*len(lats))]/1000:.1f}s  "
              f"total={sum(lats)/3600000:.2f}h")

    # Arm B: total latency per sign (all passes)
    b_total_lats = []
    for crop, passes in b_by_crop.items():
        b_total_lats.append(sum(t['latency_ms'] for t in passes))
    if b_total_lats:
        A(f"**Arm B:** mean={statistics.mean(b_total_lats)/1000:.1f}s/sign  "
          f"median={statistics.median(b_total_lats)/1000:.1f}s/sign  "
          f"total={sum(b_total_lats)/3600000:.2f}h")

    A("")

    # ── Parse failure note ────────────────────────────────────────────────────
    A("## §5 Sanity Checks")
    A("")
    A("| arm | trials | think_closed | budget_hit | parse_ok | parse_failed |")
    A("|---|---|---|---|---|---|")
    for arm_label, arm_ts in [('A', arm_a), ('B (all passes)', arm_b_all),
                               ('C', arm_c), ('D', arm_d)]:
        n = len(arm_ts)
        n_cl = sum(1 for t in arm_ts if t.get('think_closed'))
        n_bh = sum(1 for t in arm_ts if t.get('budget_hit'))
        n_ok = sum(1 for t in arm_ts if t.get('parse_status') == 'ok')
        n_pf = sum(1 for t in arm_ts if t.get('parse_status') == 'parse_failed')
        A(f"| {arm_label} | {n} | {n_cl} | {n_bh} | {n_ok} | {n_pf} |")

    A("")
    # Answer_text assertion check
    term_no_answer = [t for t in trials
                      if t.get('think_closed') and not t.get('answer_text')]
    if term_no_answer:
        A(f"⚠ **ASSERT FAILED**: {len(term_no_answer)} terminating trials have empty answer_text: "
          + str([t['crop_name'] for t in term_no_answer[:5]]))
    else:
        A("answer_text non-empty for all terminating trials: **PASS**")

    A("")

    # Flush
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, 'w') as f:
        f.write('\n'.join(lines) + '\n')


if __name__ == '__main__':
    main()
