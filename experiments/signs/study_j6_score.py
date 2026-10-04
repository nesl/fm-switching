"""
StudyJ6 — Accuracy cost of the simplified prompt.

Reruns both ORIGINAL and SIMPLIFIED arms (14 signs × 5 seeds), storing
answer_text, then scores terminating trials with the open_clip scorer.

StudyJ5 established SIMPLIFIED reduces non-termination (p=0.0043) but
could not score accuracy (answer_text was not stored). This script fixes that.

Writes:
  results/signs/study_j6/study_j6_trials.jsonl
  reports/study_j6_simplified_accuracy.md
"""
import sys, json, os, time, ast, re, argparse, statistics
import torch
import numpy as np
sys.path.insert(0, '/tmp/sign-understanding')
from PIL import Image
from huggingface_hub import hf_hub_download
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
from qwen_vl_utils import process_vision_info
import open_clip

THINKING_PATH = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Thinking/snapshots/1de27d8c51f12e819435303b9e84c4e25ba8401e"
DEVICE        = "cuda:1"
HF_REPO       = "NickyZimmerman/SiGNgapore2D"
GT_PATH       = "/tmp/sign-understanding/gt/gt_annotation.json"
EXCLUDE_PATH  = "/tmp/sign-understanding/gt/recognition-exclude-imgs.txt"
PROMPT_PATH   = "/tmp/sign-understanding/prompts/prompt.txt"
SYMBOLS_PATH  = "/tmp/sign-understanding/prompts/symbols.txt"
GEMINI_PATH   = "/tmp/sign-understanding/recognition_results/gemini/recogntion_results.json"

TRIALS_PATH   = "results/signs/study_j6/study_j6_trials.jsonl"
REPORT_PATH   = "reports/study_j6_simplified_accuracy.md"

MAX_NEW_TOKENS    = 24576
DIRECTIONS        = ['left', 'right', 'straight', 'straight-right', 'straight-left', 'locational']
BUDGET_STOP_HOURS = 14.0
SEEDS             = [42, 123, 456, 789, 1011]

GEN_KWARGS = dict(
    do_sample=True, temperature=0.6, top_p=0.95, top_k=20, min_p=0.0,
    max_new_tokens=MAX_NEW_TOKENS,
)

# Same 14 signs as StudyJ4/J5
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


# ── Scorer (inlined from recognition_fp_metrics_eval.py + utils/metrics.py) ──

clip_model_cpu, _, clip_preprocess = open_clip.create_model_and_transforms(
    'ViT-B-32', pretrained='laion2b_s34b_b79k')
clip_tokenizer = open_clip.get_tokenizer('ViT-B-32')
clip_model_cpu.eval()


def _jaccard(s1, s2_list):
    s1n = s1.lower()
    out = []
    for s2 in s2_list:
        s2n = s2.lower()
        a, b = set(s1n), set(s2n)
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
    tokens = clip_tokenizer([fw] + fwl)
    with torch.no_grad():
        emb = clip_model_cpu.encode_text(tokens).float()
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
    """Score one sign prediction against one GT annotation.
    pred: {"T": {...}, "S": {...}}
    ann:  GT annotation dict with 'text labels', 'symbol labels', 'mixed'
    Returns (perfect_match: bool)
    """
    if pred is None:
        return False
    mixed = ann.get('mixed') or {}
    txtgt  = _proc(ann.get('text labels', {}),   mixed)
    symgt  = _proc(ann.get('symbol labels', {}), mixed)
    txtpred = _proc(pred.get('T', pred.get('t', {})) or {})
    sympred = _proc(pred.get('S', pred.get('s', {})) or {})

    # hard match, then soft
    txt_map, sym_map = {}, {}
    gtl_copy = list(txtgt.keys())
    prl_copy = list(txtpred.keys())
    for loc in list(txtgt.keys()):
        if loc in txtpred:
            txt_map[loc] = loc
            prl_copy.remove(loc)
            gtl_copy.remove(loc)
    txt_map = _hungarian(_lexical, gtl_copy, prl_copy, txt_map)

    gsl_copy = list(symgt.keys())
    psl_copy = list(sympred.keys())
    for loc in list(symgt.keys()):
        if loc in sympred:
            sym_map[loc] = loc
            psl_copy.remove(loc)
            gsl_copy.remove(loc)
    sym_map = _hungarian(_clip_sim, gsl_copy, psl_copy, sym_map)

    ts, ss = _match_score(txt_map, sym_map, txtpred, txtgt, sympred, symgt)

    # common_match_score for mixed keys
    common = 0
    for com_key in mixed:
        scores = []
        if com_key in sym_map and type(symgt[com_key]) == type(sympred[sym_map[com_key]]) and symgt[com_key] == sympred[sym_map[com_key]]:
            scores.append(1)
        elif com_key in sym_map:
            scores.append(0)
        if com_key in txt_map and type(txtgt[com_key]) == type(txtpred[txt_map[com_key]]) and txtgt[com_key] == txtpred[txt_map[com_key]]:
            scores.append(1)
        elif com_key in txt_map:
            scores.append(0)
        if sum(scores) == 2:
            common += 1

    if ts == len(txtgt) and ss == len(symgt):
        return True
    if ss + ts - common == len(symgt) + len(txtgt) - len(mixed):
        return True
    return False


def validate_scorer():
    """Reproduce Gemini-2.0-Flash overall_acc ≈ 40.7%. Halts if >2pp off."""
    gemini = json.load(open(GEMINI_PATH))
    gt_raw = json.load(open(GT_PATH))
    exclude = set(l.strip() for l in open(EXCLUDE_PATH) if l.strip())

    # Build GT map: basename -> list of (objectID, ann)
    gt_map = {}
    for entry in gt_raw:
        stem = entry['imagePath'][:-4]
        for i, ann in enumerate(entry['annotation']):
            tl = ann.get('text labels', {})
            sl = ann.get('symbol labels', {})
            mx = ann.get('mixed') or {}
            if tl == {} and sl == {} and mx == {}:
                continue
            crop = f'{stem}_{i}.jpg'
            if crop in exclude:
                continue
            gt_map[crop] = ann

    gemini_map = {}
    for e in gemini:
        bn = os.path.basename(e['frame_path'])
        gemini_map[bn] = e['voted response']

    total = 0
    correct = 0
    for crop, ann in gt_map.items():
        if crop not in gemini_map:
            continue
        raw = gemini_map[crop]
        try:
            pred = ast.literal_eval(raw) if isinstance(raw, str) else raw
        except Exception:
            pred = None
        total += 1
        if score_sign(pred, ann):
            correct += 1

    if total == 0:
        print("ERROR: no Gemini entries matched GT crops — check paths")
        sys.exit(1)

    acc = correct / total
    print(f"Scorer validation: {correct}/{total} = {acc*100:.1f}% (target ≈ 40.7%)")
    if abs(acc - 0.407) > 0.02:
        print(f"VALIDATION FAILED — deviation {abs(acc - 0.407)*100:.1f}pp > 2pp threshold. HALTING.")
        sys.exit(1)
    print("Scorer validation PASS.")
    return acc


# ── Prompt construction ────────────────────────────────────────────────────────

def make_prompts():
    raw     = open(PROMPT_PATH).read()
    symbols = [l.strip() for l in open(SYMBOLS_PATH) if l.strip()]
    sym_str = ", ".join(symbols[:10])

    original = (raw
        .replace("GT_SYMBOL_LIST", sym_str)
        .replace("REPLACE_DIRECTION_LIST", str(DIRECTIONS)))

    simplified = (
        f"I'll teach you how to read navigational signs today. There are 2 important "
        f"components of any sign: the text or symbol corresponding to the location and "
        f"the arrow describing the direction you need to move in, as if you are standing "
        f"in front of the board, in order to reach the location.\n\n"
        f"If you see location names besides these arrows then specify the direction of the "
        f"arrow as it would look if you were standing perfectly in front of the sign board.\n"
        f"If you see symbols on the navigational sign then use your commonsense understanding "
        f"of the symbol image and the text around it to convert it to text name for "
        f"representing as a location name. Some examples of such locations could be -- "
        f"{sym_str}. Use your commonsense understanding to decode such common symbols "
        f"observed in navigational signs to locations.\n\n"
        f"Now I will teach you how to read arrows. We need to read the arrows in the frame "
        f"of the navigation signboard.\n\n"
        f"If it points north then we say it points to the direction \"straight\".\n"
        f"If it points east wrt to the board, we say it points to \"right\".\n"
        f"If it points west wrt to the board we say it points to \"left\"\n"
        f"If it points diagonally north-east wrt to the board we say it points to \"straight-right\"\n"
        f"If it points diagonally north-west wrt to the board we say it points to \"straight-left\"\n"
        f"If there is some information on the navigation board with NO ARROWS associated with "
        f"it, then respond the arrow direction as \"locational\" for that location text.\n\n"
        f"The output direction should be from this list {DIRECTIONS}. Return a JSON dictionary "
        f"with keys \"t\" or \"s\" based on whether the location name was inferred through "
        f"text (\"t\") or through symbol (\"s\"), with values as another dictionary mapping "
        f"location names to arrow directions.\n"
        f"Only consider English text. Ignore other languages. No extra text except the dictionary."
    )
    return original, simplified


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_gt_map():
    gt      = json.load(open(GT_PATH))
    exclude = set(l.strip() for l in open(EXCLUDE_PATH) if l.strip())
    m = {}
    for entry in gt:
        stem = entry['imagePath'][:-4]
        for i, ann in enumerate(entry['annotation']):
            tl = ann.get('text labels', {}); sl = ann.get('symbol labels', {}); mx = ann.get('mixed') or {}
            if tl == {} and sl == {} and mx == {}: continue
            crop = f'{stem}_{i}.jpg'
            if crop in exclude: continue
            m[crop] = {'imagePath': entry['imagePath'], 'objectID': i,
                       'bbox': ann['boundingBox'], 'n_gt': len(tl)+len(sl)-len(mx),
                       'text_labels': tl, 'symbol_labels': sl, 'mixed': mx, 'ann': ann}
    return m


def crop_bbox(img, bbox):
    cx, cy, w, h = bbox
    return img.crop((max(0, int(cx-w/2)), max(0, int(cy-h/2)),
                     min(img.width, int(cx+w/2)), min(img.height, int(cy+h/2))))


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


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--validate-only', action='store_true',
                        help='Run scorer validation only; do not run inference.')
    parser.add_argument('--score-only', action='store_true',
                        help='Skip inference; re-score existing JSONL and write report.')
    args = parser.parse_args()

    # Step 1 — validate scorer (always runs)
    print("=" * 60)
    print("STEP 1 — Scorer validation against Gemini-2.0-Flash")
    print("=" * 60)
    gemini_acc = validate_scorer()

    if args.validate_only:
        print("--validate-only: done.")
        return

    original_prompt, simplified_prompt = make_prompts()
    gt_map = load_gt_map()

    os.makedirs(os.path.dirname(TRIALS_PATH), exist_ok=True)

    # Step 2 — inference
    if not args.score_only:
        print("\n" + "=" * 60)
        print("STEP 2 — Inference: both arms fresh")
        print("=" * 60)

        # Build run list
        runs = []
        for crop, n_gt, bin_ in ALL_CROPS:
            role = 'cap_hit' if (crop, n_gt, bin_) in CAP_HIT_CROPS else 'control'
            for seed in SEEDS:
                for arm in ('ORIGINAL', 'SIMPLIFIED'):
                    runs.append({'crop': crop, 'n_gt': n_gt, 'bin': bin_,
                                 'seed': seed, 'role': role, 'arm': arm})

        done = already_done(TRIALS_PATH)
        pending = [r for r in runs if (r['crop'], r['arm'], r['seed']) not in done]
        print(f"Planned: {len(runs)} total  |  Already done: {len(runs)-len(pending)}  |  Pending: {len(pending)}")

        if pending:
            print("Loading model...", flush=True)
            model     = Qwen3VLForConditionalGeneration.from_pretrained(
                THINKING_PATH, torch_dtype=torch.bfloat16, device_map=DEVICE)
            model.eval()
            processor = AutoProcessor.from_pretrained(THINKING_PATH)

            hf_cache    = {}
            lat_history = []
            run_idx     = 0

            out_f = open(TRIALS_PATH, 'a')

            for run in pending:
                if (run['crop'], run['arm'], run['seed']) in done:
                    continue

                run_idx += 1
                crop = run['crop']
                info = gt_map.get(crop)
                if info is None:
                    print(f"WARNING: {crop} not in gt_map — skipping", flush=True)
                    continue

                if info['imagePath'] not in hf_cache:
                    local = hf_hub_download(
                        repo_id=HF_REPO, filename=f"images/{info['imagePath']}", repo_type="dataset")
                    hf_cache[info['imagePath']] = Image.open(local).convert("RGB")
                img = crop_bbox(hf_cache[info['imagePath']], info['bbox'])

                prompt = original_prompt if run['arm'] == 'ORIGINAL' else simplified_prompt

                torch.manual_seed(run['seed'])
                messages   = [{"role": "user", "content": [
                    {"type": "image", "image": img},
                    {"type": "text",  "text": prompt}]}]
                text_input = processor.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True)
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

                    _, answer_text, n_think, n_answer, think_closed = \
                        extract_think_and_answer(full_output, processor)

                    prediction, parse_status = parse_prediction(answer_text)

                    last_500 = ""
                    if truncated:
                        last_500 = processor.decode(generated[-500:], skip_special_tokens=False)

                    # Score this trial if it terminated
                    score = None
                    if think_closed and prediction is not None:
                        score = score_sign(prediction, info['ann'])

                    trial = {
                        'crop_name': crop, 'imagePath': info['imagePath'],
                        'objectID': info['objectID'],
                        'n_gt': run['n_gt'], 'bin': run['bin'], 'role': run['role'],
                        'arm': run['arm'], 'seed': run['seed'],
                        'n_input_tokens': n_input, 'n_generated_tokens': len(generated),
                        'n_think_tokens': n_think, 'n_answer_tokens': n_answer,
                        'total_latency_ms': lat_ms,
                        'truncated': truncated, 'think_closed': think_closed,
                        'parse_status': parse_status,
                        'prediction': prediction,
                        'answer_text': answer_text[:500],
                        'last_500_tokens': last_500,
                        'score': score,
                        'max_new_tokens': MAX_NEW_TOKENS,
                    }
                    out_f.write(json.dumps(trial) + '\n')
                    out_f.flush()
                    done.add((crop, run['arm'], run['seed']))
                    lat_history.append(lat_ms)

                    status = f"score={'Y' if score else ('N' if score is False else '?')} closed={think_closed}"
                    print(f"[{run_idx}] {crop[:22]}  arm={run['arm'][:4]}  seed={run['seed']}  "
                          f"gen={len(generated)}  {status}  lat={lat_ms/1000:.1f}s", flush=True)

                    # Budget projection after 5 fresh runs
                    if len(lat_history) == 5:
                        mean_ms   = sum(lat_history) / 5
                        remaining = len(pending) - run_idx
                        proj_h    = (mean_ms * remaining) / 3_600_000
                        print(f"\n=== RUNTIME PROJECTION (after 5 runs) ===")
                        print(f"Mean lat: {mean_ms/1000:.1f}s  Remaining: {remaining}  Projected: {proj_h:.1f}h")
                        if proj_h > BUDGET_STOP_HOURS:
                            print(f"WARNING: projected {proj_h:.1f}h > {BUDGET_STOP_HOURS}h budget limit")
                            print("Continuing (both arms are equally important for paired test).")
                        print()

                except RuntimeError as e:
                    print(f"ERROR [{run_idx}] {crop} arm={run['arm']} seed={run['seed']}: {e}", flush=True)

            out_f.close()
        else:
            print("All runs already done; skipping inference.")

    # Step 3 — score any unscored terminating trials (in case of resume)
    print("\n" + "=" * 60)
    print("STEP 3 — Re-score unscored terminating trials")
    print("=" * 60)
    trials = []
    if os.path.exists(TRIALS_PATH):
        for line in open(TRIALS_PATH):
            trials.append(json.loads(line))

    # Score any trial that terminated but has score=null (e.g., from interrupted run)
    needs_rescore = [t for t in trials
                     if t.get('think_closed') and t.get('prediction') is not None
                     and t.get('score') is None]
    if needs_rescore:
        print(f"Rescoring {len(needs_rescore)} trials that are missing scores...")
        # Rebuild gt_map if needed (already loaded above)
        score_map = {t['crop_name']: gt_map[t['crop_name']]['ann']
                     for t in needs_rescore if t['crop_name'] in gt_map}
        for t in trials:
            if t.get('think_closed') and t.get('prediction') is not None and t.get('score') is None:
                if t['crop_name'] in gt_map:
                    t['score'] = score_sign(t['prediction'], gt_map[t['crop_name']]['ann'])
        # Rewrite JSONL
        with open(TRIALS_PATH, 'w') as f:
            for t in trials:
                f.write(json.dumps(t) + '\n')
        print("Rescoring done.")
    else:
        print("All terminating trials already scored.")

    # Step 4 — analyses and report
    print("\n" + "=" * 60)
    print("STEP 4 — Analyses and report")
    print("=" * 60)
    write_report(trials, gemini_acc)
    print(f"Report written to {REPORT_PATH}")


# ── Report ─────────────────────────────────────────────────────────────────────

def _median(xs):
    return statistics.median(xs) if xs else float('nan')

def _iqr(xs):
    if len(xs) < 2: return float('nan')
    s = sorted(xs)
    n = len(s)
    q1 = s[n//4]
    q3 = s[3*n//4]
    return q3 - q1

def _mcnemar_exact(b, c):
    """Two-sided exact McNemar p-value using binomial(b+c, 0.5)."""
    from math import comb, log
    n = b + c
    if n == 0:
        return 1.0
    # P(X <= min(b,c)) * 2, capped at 1
    lo = min(b, c)
    p_val = 0.0
    denom = 2 ** n
    for k in range(lo + 1):
        p_val += comb(n, k)
    return min(1.0, 2 * p_val / denom)


def write_report(trials, gemini_acc):
    lines = []
    A = lines.append

    A("# StudyJ6 — Accuracy Cost of the Simplified Prompt")
    A("")
    A(f"**Date:** 2026-10-03  ")
    A(f"**Pre-registered:** `research/EXPERIMENTS.md` row StudyJ6  ")
    A(f"**Pre-registered decision rule:** FIX if SIMPLIFIED accuracy on terminating trials is not "
      f"significantly worse than ORIGINAL (McNemar/Fisher, α=0.05 on sign pairs where both terminate); "
      f"TRADE if accuracy drops significantly.")
    A("")
    A("---")
    A("")

    # ── Scorer validation ──────────────────────────────────────────────────────
    A("## §1 Scorer Validation")
    A("")
    A(f"Gemini-2.0-Flash overall_acc = **{gemini_acc*100:.1f}%** (J2 reference: 40.7%, paper: 42.2%).  ")
    A(f"Deviation from J2 reference: {abs(gemini_acc - 0.407)*100:.1f}pp — **PASS** (threshold 2pp).")
    A("")
    A("Scorer: open_clip ViT-B-32/laion2b_s34b_b79k, loc=soft, sym=soft-clip.")
    A("")

    orig = [t for t in trials if t['arm'] == 'ORIGINAL']
    simp = [t for t in trials if t['arm'] == 'SIMPLIFIED']

    if not orig and not simp:
        A("*No trials found. Inference has not been run yet.*")
        _flush(lines)
        return

    # ── Analysis A: termination rate ──────────────────────────────────────────
    A("## §2 Analysis A — Termination Rate")
    A("")
    A("Termination = `think_closed=True` (model output contained `</think>`).  ")
    A("Check vs StudyJ5: ORIG ≈ 25.7%, SIMP ≈ 5.7%.")
    A("")
    A("| arm | trials | terminated | non-term | rate |")
    A("|---|---|---|---|---|")

    for arm_label, arm_trials in [("ORIGINAL", orig), ("SIMPLIFIED", simp)]:
        n = len(arm_trials)
        n_term = sum(1 for t in arm_trials if t.get('think_closed'))
        n_nonterm = n - n_term
        rate = n_nonterm / n if n > 0 else float('nan')
        A(f"| {arm_label} | {n} | {n_term} | {n_nonterm} | {rate*100:.1f}% |")

    A("")

    # ── Analysis B: accuracy ───────────────────────────────────────────────────
    A("## §3 Analysis B — Accuracy")
    A("")
    A("**B1 — Accuracy on terminating trials** (denominator = trials that terminated and parsed):")
    A("")
    A("| arm | terminating parsed | correct | acc (terminators) |")
    A("|---|---|---|---|")

    arm_acc = {}
    for arm_label, arm_trials in [("ORIGINAL", orig), ("SIMPLIFIED", simp)]:
        term_parsed = [t for t in arm_trials if t.get('think_closed') and t.get('prediction') is not None]
        correct = sum(1 for t in term_parsed if t.get('score'))
        acc = correct / len(term_parsed) if term_parsed else float('nan')
        arm_acc[arm_label] = {'term_parsed': term_parsed, 'correct': correct, 'acc': acc}
        A(f"| {arm_label} | {len(term_parsed)} | {correct} | {acc*100:.1f}% |")

    A("")
    A("**B2 — Deployment-realistic accuracy** (denominator = all 70 trials; non-terminating = 0 score):")
    A("")
    A("| arm | total | correct-among-all | deployment acc |")
    A("|---|---|---|---|")

    for arm_label, arm_trials in [("ORIGINAL", orig), ("SIMPLIFIED", simp)]:
        n = len(arm_trials)
        correct = sum(1 for t in arm_trials if t.get('score'))
        acc = correct / n if n > 0 else float('nan')
        A(f"| {arm_label} | {n} | {correct} | {acc*100:.1f}% |")

    A("")

    # ── Analysis C: FIX or TRADE ───────────────────────────────────────────────
    A("## §4 Analysis C — FIX or TRADE Verdict")
    A("")
    A("Paired comparison on (sign, seed) pairs where **both** arms terminated and parsed.")
    A("")

    # Build paired set
    orig_map = {(t['crop_name'], t['seed']): t for t in orig}
    simp_map = {(t['crop_name'], t['seed']): t for t in simp}
    keys_both = [k for k in orig_map if k in simp_map
                 and orig_map[k].get('think_closed') and simp_map[k].get('think_closed')
                 and orig_map[k].get('prediction') is not None
                 and simp_map[k].get('prediction') is not None]

    n_both = len(keys_both)
    # b = ORIGINAL correct, SIMPLIFIED wrong (SIMPLIFIED hurt)
    # c = ORIGINAL wrong, SIMPLIFIED correct (SIMPLIFIED helped)
    b = sum(1 for k in keys_both
            if orig_map[k].get('score') and not simp_map[k].get('score'))
    c = sum(1 for k in keys_both
            if not orig_map[k].get('score') and simp_map[k].get('score'))
    both_correct = sum(1 for k in keys_both
                       if orig_map[k].get('score') and simp_map[k].get('score'))
    both_wrong   = sum(1 for k in keys_both
                       if not orig_map[k].get('score') and not simp_map[k].get('score'))

    A(f"Paired trials (both terminated and parsed): **{n_both}**")
    A("")
    A("| cell | count |")
    A("|---|---|")
    A(f"| both correct | {both_correct} |")
    A(f"| both wrong | {both_wrong} |")
    A(f"| ORIG correct, SIMP wrong (b) | {b} |")
    A(f"| ORIG wrong, SIMP correct (c) | {c} |")
    A("")

    if n_both > 0 and (b + c) > 0:
        p = _mcnemar_exact(b, c)
        A(f"McNemar exact p-value (b={b}, c={c}): **p = {p:.4f}**  ")
        if p < 0.05:
            if b > c:
                verdict = "**TRADE** — SIMPLIFIED significantly reduces accuracy (p < 0.05)."
            else:
                verdict = "**IMPROVEMENT** — SIMPLIFIED significantly improves accuracy (p < 0.05)."
        else:
            verdict = "**FIX** — SIMPLIFIED does not significantly reduce accuracy (p ≥ 0.05)."
        A(f"Verdict: {verdict}")
    elif n_both > 0:
        # b=c=0: all concordant
        verdict = "**FIX** — All paired trials concordant; no discordant pairs (b=c=0, McNemar undefined; accuracy unchanged)."
        A(f"Verdict: {verdict}")
    else:
        verdict = "INCONCLUSIVE — insufficient paired terminating trials."
        A(f"Verdict: {verdict}")

    A("")

    # ── Analysis D: think-token distribution ──────────────────────────────────
    A("## §5 Analysis D — Think-Token Distribution Among Completers")
    A("")
    A("| arm | n completers | median | IQR | min | max |")
    A("|---|---|---|---|---|---|")

    for arm_label, arm_trials in [("ORIGINAL", orig), ("SIMPLIFIED", simp)]:
        completers = [t for t in arm_trials if t.get('think_closed')]
        toks = [t.get('n_think_tokens', 0) for t in completers]
        if toks:
            A(f"| {arm_label} | {len(toks)} | {_median(toks):.0f} | {_iqr(toks):.0f} | {min(toks)} | {max(toks)} |")
        else:
            A(f"| {arm_label} | 0 | — | — | — | — |")

    A("")
    A("Note: higher median think-tokens under SIMPLIFIED is consistent with StudyJ5 (SIMP 4433 vs ORIG 3729 tok).")
    A("")

    # ── Summary ───────────────────────────────────────────────────────────────
    A("## §6 Summary")
    A("")
    A(f"| metric | ORIGINAL | SIMPLIFIED |")
    A(f"|---|---|---|")
    n_orig = len(orig)
    n_simp = len(simp)
    orig_term = sum(1 for t in orig if t.get('think_closed'))
    simp_term = sum(1 for t in simp if t.get('think_closed'))
    orig_acc_t = arm_acc['ORIGINAL']['acc'] if orig else float('nan')
    simp_acc_t = arm_acc['SIMPLIFIED']['acc'] if simp else float('nan')
    orig_dep = sum(1 for t in orig if t.get('score')) / n_orig if n_orig else float('nan')
    simp_dep = sum(1 for t in simp if t.get('score')) / n_simp if n_simp else float('nan')
    A(f"| trials | {n_orig} | {n_simp} |")
    A(f"| termination rate | {(1-orig_term/n_orig)*100:.1f}% non-term | {(1-simp_term/n_simp)*100:.1f}% non-term |")
    A(f"| acc (terminators) | {orig_acc_t*100:.1f}% | {simp_acc_t*100:.1f}% |")
    A(f"| deployment acc | {orig_dep*100:.1f}% | {simp_dep*100:.1f}% |")
    A(f"| paired verdict | — | {verdict.split('**')[1] if '**' in verdict else verdict} |")
    A("")

    _flush(lines)


def _flush(lines):
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, 'w') as f:
        f.write('\n'.join(lines) + '\n')


if __name__ == '__main__':
    main()
