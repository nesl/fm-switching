"""
StudyT — offline scorer for SiGNgapore2D trials (scoring is decoupled from generation).

The scorer body below is copied verbatim from experiments/signs/study_p_retry_vs_scale.py
(L63-254: score_sign + validate_scorer), itself inlined from Sign-Understanding's
recognition_fp_metrics_eval.py + utils/metrics.py. Symbol matching uses open_clip
ViT-B-32/laion2b_s34b_b79k text similarity on CPU.

Usage:
  python experiments/signs/study_t_score.py --validate     # Gemini-2.0-Flash ≈40.7% check -> scorer_validation.json
  python experiments/signs/study_t_score.py                # score trials -> study_t_scores_h100nvl.jsonl

Scoring rule (mirrors StudyP run_arm): a trial is score-eligible only if the thinking trace
closed (thinking arm) or EOS was reached before the budget (instruct arm), and the answer
parsed. Non-eligible trials score 0 for accuracy (non-terminating = 0) and are labelled.
Accuracy is labelled VALIDATED only if scorer_validation.json shows pass=true.
"""
import sys, json, os, ast, argparse
from pathlib import Path
import torch
import numpy as np
import open_clip

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

GT_PATH      = "/tmp/sign-understanding/gt/gt_annotation.json"
EXCLUDE_PATH = "/tmp/sign-understanding/gt/recognition-exclude-imgs.txt"
GEMINI_PATH  = "/tmp/sign-understanding/recognition_results/gemini/recogntion_results.json"
TRIALS_PATH  = "results/signs/study_t/study_t_trials_h100nvl.jsonl"
SCORES_PATH  = "results/signs/study_t/study_t_scores_h100nvl.jsonl"
VALID_PATH   = "results/signs/study_t/scorer_validation.json"
GEMINI_TARGET = 0.407
TOLERANCE     = 0.02

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


# ── GT map (verbatim logic from study_p_retry_vs_scale.build_gt_map) ──────────

def build_gt_map():
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
            m[crop] = {'imagePath': entry['imagePath'], 'objectID': i, 'bbox': ann['boundingBox'],
                       'n_gt': len(tl) + len(sl) - len(mx), 'ann': ann}
    return m


def validate_scorer(gt_map_full):
    """Same logic as study_p_retry_vs_scale.validate_scorer, but records instead of exiting."""
    gemini = json.load(open(GEMINI_PATH))
    gemini_map = {os.path.basename(e['frame_path']): e['voted response'] for e in gemini}
    total = correct = unparsed = 0
    for crop, info in gt_map_full.items():
        if crop not in gemini_map:
            continue
        raw = gemini_map[crop]
        try:
            pred = ast.literal_eval(raw) if isinstance(raw, str) else raw
        except Exception:
            pred = None
            unparsed += 1
        total += 1
        if score_sign(pred, info['ann']):
            correct += 1
    acc = correct / total if total else float('nan')
    ok = total > 0 and abs(acc - GEMINI_TARGET) <= TOLERANCE
    return dict(gemini_entries=len(gemini), gt_crops_after_exclusion=len(gt_map_full),
                matched_denominator=total, correct=correct, gemini_unparsed=unparsed,
                accuracy=round(acc, 4), target=GEMINI_TARGET, tolerance_pp=100 * TOLERANCE,
                deviation_pp=round(100 * abs(acc - GEMINI_TARGET), 2), passed=bool(ok))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--validate', action='store_true')
    ap.add_argument('--trials', default=TRIALS_PATH)
    ap.add_argument('--out', default=SCORES_PATH)
    args = ap.parse_args()
    gt_map_full = build_gt_map()

    if args.validate:
        from _provenance import stamp
        import subprocess
        r = validate_scorer(gt_map_full)
        r['sign_understanding_commit'] = subprocess.run(
            ['git', '-C', '/tmp/sign-understanding', 'rev-parse', 'HEAD'],
            capture_output=True, text=True).stdout.strip()
        r['open_clip_version'] = open_clip.__version__
        r['_provenance'] = stamp(script='study_t_score.py', model='gemini-2.0-flash (stored outputs)',
                                 device='cpu', n=r['matched_denominator'], args=args)
        os.makedirs(os.path.dirname(VALID_PATH), exist_ok=True)
        Path(VALID_PATH).write_text(json.dumps(r, indent=2))
        print(f"Scorer validation: {r['correct']}/{r['matched_denominator']} = {100*r['accuracy']:.1f}% "
              f"(target 40.7%) -> {'PASS' if r['passed'] else 'FAIL — accuracy will be UNVALIDATED SCORER'}")
        return

    validated = False
    if os.path.exists(VALID_PATH):
        validated = bool(json.load(open(VALID_PATH)).get('passed'))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from study_t_signs_32b import parse_prediction
    rows = [json.loads(l) for l in open(args.trials) if l.strip()]
    with open(args.out, 'w') as f:
        for t in rows:
            info = gt_map_full[t['sign_id']]
            pred, parse_status = parse_prediction(t['answer_text'] or '')
            eligible = (t['think_closed'] is True) if t['arm'] == 'T32' else (not t['budget_hit'])
            correct = bool(eligible and pred is not None and score_sign(pred, info['ann']))
            f.write(json.dumps(dict(arm=t['arm'], budget=t['budget'], sign_id=t['sign_id'],
                                    eligible=eligible, parse_status=parse_status, correct=correct,
                                    scorer_validated=validated)) + '\n')
    print(f"scored {len(rows)} trials -> {args.out}  scorer_validated={validated}")


if __name__ == '__main__':
    main()
