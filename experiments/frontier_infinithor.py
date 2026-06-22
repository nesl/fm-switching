"""
Infini-THOR / NiEH Gate + Frontier
====================================
Evaluates representation compressibility on the Needles in the Embodied Haystack
(NiEH and NsiEH) recall tasks from PEARLS-Lab/infini-thor.

Architecture:
  traj.txt (multimodal token format, image placeholders stripped) →
  representation ladder → Qwen2.5-7B → answer

Trajectory format (from metadata.tar):
  <|goal|>Your main goal: put some keychain on sidetable<|goal|>
  <image>
  <|plan|>Plan: go to the diningtable<|plan|>
  <|act|>LookDown<|act|><image>
  <|act|>PickupObject KeyChain<|act|><image>
  <|plan|>Plan: put the KeyChain in the SideTable<|plan|>
  <|act|>PutObject KeyChain SideTable<|act|><image>
  ...

After stripping <image> tokens and reformatting: ~1,500-2,500 tokens per trajectory.
Anchors are GUARANTEED: PutObject X Y is logged for every placement event.

Text source: simulator oracle logs (not a VLM captioner). No perception-stage loss.

Conditions: blind | window-10 | summary-80 | summary-200 | full | shuffled

Headline: multi-clue (NsiEH) non-salient subset — strongest incompressibility case.
Secondary: single-clue (NiEH) non-salient subset.

Oracle guard: every representation is built from traj.txt ONLY.
              gt_steps, gt_img_idx, and all evidence fields are NEVER fed as input.

Scoring:
  Primary: exact string match against answer list entries (case-insensitive, normalised)
  Secondary: Qwen2.5-7B LLM judge for near-matches ("SideTable" ≈ "Side Table")

Salient split:
  Salient   = answer is among top-3 most frequent receptacles in this trajectory
  Non-salient = answer is NOT among top-3 most frequent receptacles

Usage:
  # Gate: multi-clue n=100, single-clue n=50
  CUDA_VISIBLE_DEVICES=1 python experiments/frontier_infinithor.py --gate

  # Full frontier (after gate passes)
  CUDA_VISIBLE_DEVICES=1 python experiments/frontier_infinithor.py --frontier
"""

import argparse
import ast
import gc
import json
import random
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).parent.parent))
from experiments._provenance import stamp

# ── Constants ──────────────────────────────────────────────────────────────────

REASONING_MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"
DATA_DIR           = Path(__file__).parent.parent / "data" / "infinithor"
RESULTS            = Path(__file__).parent.parent / "results"
TRAJ_DIR_TEST      = DATA_DIR / "traj_test"
TRAJ_DIR_TRAIN     = DATA_DIR / "traj"
SC_CSV             = DATA_DIR / "qa_set_nieh_single_clue.csv"
MC_CSV             = DATA_DIR / "qa_set_nsieh_multi_clue.csv"
DEVICE_STR         = "cuda:0"

# ── Prompts ────────────────────────────────────────────────────────────────────

FULL_PROMPT = (
    "You are reviewing a log of a robot's actions in a household environment.\n\n"
    "=== TRAJECTORY LOG ===\n{context}\n=== END LOG ===\n\n"
    "Question: {question}\n\n"
    "Answer with only the object or location name, as concisely as possible "
    "(e.g. 'SideTable', 'Dresser', 'Pen'). Do not explain.\nAnswer:"
)

BLIND_PROMPT = (
    "Question about a household robot's past actions: {question}\n\n"
    "Answer with only the object or location name, as concisely as possible. "
    "Do not explain.\nAnswer:"
)

SUMMARY_PROMPT = (
    "Summarize the following robot action log in plain English, preserving the "
    "names of all objects and the receptacles they were placed on or picked from. "
    "Under {max_tokens} tokens.\n\n{context}\n\nSummary:"
)

JUDGE_PROMPT = (
    "Do these two answers refer to the same object or location?\n"
    "Answer A: {pred}\nAnswer B: {gold}\n"
    "YES if same or very similar (e.g. 'SideTable' = 'Side Table', "
    "'CoffeeTable' = 'coffee table'). NO if clearly different.\n"
    "Reply with only YES or NO."
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_json(path: Path):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return None


def _save_json(path: Path, obj) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    tmp.replace(path)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text.lower().strip())


def _find_traj(traj_id: str) -> Path | None:
    for d in [TRAJ_DIR_TEST, TRAJ_DIR_TRAIN]:
        p = d / f"{traj_id}.txt"
        if p.exists():
            return p
    return None


def _parse_traj_token_format(raw: str) -> str:
    """Convert the <|goal|>/<|plan|>/<|act|>/<image> token format to readable oracle text.

    The traj.txt files use a multimodal LLM token format. After stripping <image>
    placeholders, the remaining text contains all oracle information:
      - Goals: "Your main goal: put some keychain on sidetable"
      - Plans: "Plan: put the KeyChain in the SideTable"
      - Actions: "PickupObject KeyChain", "PutObject KeyChain SideTable"

    Navigation-only actions (MoveAhead, RotateLeft, LookDown, etc.) are collapsed
    to avoid padding out the context with uninformative steps.
    """
    NAV_ACTIONS = {
        "MoveAhead", "MoveBack", "RotateRight", "RotateLeft",
        "LookUp", "LookDown", "TeleportFull", "Teleport", "Pass", "Done",
    }
    lines = []
    # Extract tagged spans
    goals = re.findall(r'<\|goal\|>(.*?)<\|goal\|>', raw, re.DOTALL)
    plans = re.findall(r'<\|plan\|>(.*?)<\|plan\|>', raw, re.DOTALL)
    acts  = re.findall(r'<\|act\|>(.*?)<\|act\|>', raw, re.DOTALL)

    # Interleave in document order using character positions
    spans = []
    for m in re.finditer(r'<\|goal\|>(.*?)<\|goal\|>', raw, re.DOTALL):
        spans.append((m.start(), "GOAL", m.group(1).strip()))
    for m in re.finditer(r'<\|plan\|>(.*?)<\|plan\|>', raw, re.DOTALL):
        spans.append((m.start(), "PLAN", m.group(1).strip()))
    for m in re.finditer(r'<\|act\|>(.*?)<\|act\|>', raw, re.DOTALL):
        txt = m.group(1).strip()
        if txt and not txt.startswith("<image>"):
            action_word = txt.split()[0] if txt.split() else ""
            spans.append((m.start(), "ACT", txt))
    spans.sort(key=lambda x: x[0])

    prev_nav_count = 0
    for _, tag, txt in spans:
        if tag == "GOAL":
            lines.append(f"[Goal] {txt}")
            prev_nav_count = 0
        elif tag == "PLAN":
            lines.append(f"[Plan] {txt}")
            prev_nav_count = 0
        elif tag == "ACT":
            action_word = txt.split()[0] if txt.split() else ""
            if action_word in NAV_ACTIONS:
                prev_nav_count += 1
                # Emit a nav summary every 10 steps to preserve sequence length info
                if prev_nav_count % 10 == 0:
                    lines.append(f"[Nav] ... ({prev_nav_count} navigation steps)")
            else:
                if prev_nav_count > 0:
                    lines.append(f"[Nav] ({prev_nav_count} navigation steps)")
                    prev_nav_count = 0
                lines.append(f"[Action] {txt}")
    return "\n".join(lines)


def load_traj_text(traj_id: str) -> str | None:
    p = _find_traj(traj_id)
    if p is None:
        return None
    raw = p.read_text(encoding="utf-8", errors="replace")
    return _parse_traj_token_format(raw)


def parse_answer_list(answer_str: str) -> list[str]:
    try:
        items = ast.literal_eval(answer_str)
        return [str(i).strip() for i in items]
    except Exception:
        return [answer_str.strip()]


def exact_match(pred: str, gold_list: list[str]) -> int:
    pred_n = _normalize(pred)
    return int(any(pred_n == _normalize(g) for g in gold_list))


def partial_match(pred: str, gold_list: list[str]) -> int:
    pred_n = _normalize(pred)
    return int(any(_normalize(g) in pred_n or pred_n in _normalize(g)
                   for g in gold_list))


# ── Trajectory analysis ───────────────────────────────────────────────────────

# Common receptacle names in AI2-THOR (for salient detection)
_RECEPTACLE_WORDS = {
    "sidetable", "coffeetable", "diningtable", "desk", "dresser", "shelf",
    "sofa", "bed", "counter", "countertop", "fridge", "microwave", "sink",
    "bathtub", "toilet", "tvstand", "ottoman", "cabinet", "drawer",
    "garbage", "garbagecan", "laundry", "hamper", "safe",
}


def detect_top_receptacles(traj_text: str, k: int = 3) -> list[str]:
    """Return the k most frequently mentioned receptacle-like nouns in the trajectory.

    Counts from [Action] PutObject X Y lines, which are the most reliable signal.
    Falls back to scanning all lines for receptacle words.
    """
    counts: Counter = Counter()
    for line in traj_text.splitlines():
        # PutObject X Receptacle — count the receptacle (last word)
        m = re.match(r'\[Action\] PutObject\s+\S+\s+(\S+)', line)
        if m:
            counts[m.group(1).lower()] += 1
            continue
        # Fallback: scan for receptacle words
        line_n = _normalize(line)
        for r in _RECEPTACLE_WORDS:
            if r in line_n:
                counts[r] += 1
    return [r for r, _ in counts.most_common(k)]


def is_salient(gold_list: list[str], top_receptacles: list[str]) -> bool:
    gold_ns = [_normalize(g) for g in gold_list]
    for r in top_receptacles:
        for gn in gold_ns:
            if r in gn or gn in r:
                return True
    return False


# ── Text representations ──────────────────────────────────────────────────────

def get_steps(traj_text: str) -> list[str]:
    """Return non-empty lines as individual observation steps."""
    return [l for l in traj_text.splitlines() if l.strip()]


def build_context(steps: list[str], condition: str,
                  summary_fn=None, shuffle_seed: int = 42) -> str | None:
    if condition == "blind":
        return None
    if condition == "full":
        return "\n".join(steps)
    if condition.startswith("window-"):
        k = int(condition.split("-")[1])
        return "\n".join(steps[-k:])
    if condition == "shuffled":
        rng = random.Random(shuffle_seed)
        shuffled = list(steps)
        rng.shuffle(shuffled)
        return "\n".join(shuffled)
    if condition in ("summary-80", "summary-200"):
        max_tok = 80 if condition == "summary-80" else 200
        if summary_fn is None:
            return None
        return summary_fn("\n".join(steps), max_tok)
    return None


# ── LLM ──────────────────────────────────────────────────────────────────────

def load_llm():
    from transformers import AutoTokenizer, AutoModelForCausalLM
    print(f"Loading LLM: {REASONING_MODEL_ID} ...")
    tok = AutoTokenizer.from_pretrained(REASONING_MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(
        REASONING_MODEL_ID, torch_dtype=torch.float16, device_map=DEVICE_STR,
    )
    model.eval()
    return model, tok


def _llm_run(model, tok, prompt: str, max_new: int = 40) -> str:
    formatted = tok.apply_chat_template(
        [{"role": "user", "content": prompt}],
        tokenize=False, add_generation_prompt=True,
    )
    inputs = tok(formatted, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(
            **inputs, max_new_tokens=max_new, do_sample=False,
            pad_token_id=tok.eos_token_id,
        )
    gen = out[0][inputs["input_ids"].shape[1]:]
    return tok.decode(gen, skip_special_tokens=True).strip()


def count_tokens(tok, text: str) -> int:
    return len(tok.encode(text, add_special_tokens=False))


def evidence_distance(steps: list[str], gold_list: list[str]) -> dict:
    """Compute how far the evidence steps are from the end of the trajectory.

    Returns:
      last_evidence_step: index of the last step containing any gold answer word
      steps_from_end: len(steps) - 1 - last_evidence_step
      distance_bin: 'near' (≤10 steps from end) | 'mid' (11-30) | 'far' (>30)
    """
    gold_ns = [_normalize(g) for g in gold_list]
    last_evidence = -1
    for i, step in enumerate(steps):
        step_n = _normalize(step)
        if any(gn in step_n for gn in gold_ns if gn):
            last_evidence = i
    if last_evidence < 0:
        return {"last_evidence_step": -1, "steps_from_end": -1, "distance_bin": "not_found"}
    dist = len(steps) - 1 - last_evidence
    if dist <= 10:
        bin_ = "near"
    elif dist <= 30:
        bin_ = "mid"
    else:
        bin_ = "far"
    return {
        "last_evidence_step": last_evidence,
        "steps_from_end":     dist,
        "distance_bin":       bin_,
    }


def make_summary_fn(model, tok):
    def _summarize(full_text: str, max_tokens: int) -> str:
        prompt = SUMMARY_PROMPT.format(max_tokens=max_tokens, context=full_text)
        return _llm_run(model, tok, prompt, max_new=max_tokens + 20)
    return _summarize


def answer_question(model, tok, steps: list[str], question: str,
                    condition: str, summary_fn=None) -> tuple[str, str]:
    ctx = build_context(steps, condition, summary_fn)
    if ctx is None:
        prompt = BLIND_PROMPT.format(question=question)
    else:
        prompt = FULL_PROMPT.format(context=ctx, question=question)
    raw = _llm_run(model, tok, prompt, max_new=40)
    final = raw.split("\n")[0].strip()
    return raw, final


def llm_judge(model, tok, pred: str, gold_list: list[str]) -> int:
    # Lazy: only call LLM if exact match already failed.
    if exact_match(pred, gold_list):
        return 1
    for gold in gold_list:
        prompt = JUDGE_PROMPT.format(pred=pred, gold=gold)
        resp = _llm_run(model, tok, prompt, max_new=4)
        if resp.strip().upper().startswith("YES"):
            return 1
    return 0


# ── Data loading and filtering ────────────────────────────────────────────────

def load_qa(csv_path: Path, exclude_numeric: bool = True) -> list[dict]:
    import csv
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if exclude_numeric:
                q = row["question"].lower()
                if q.startswith("how many") or q.startswith("how much"):
                    continue
                ans = parse_answer_list(row["answer"])
                if all(a.strip().isdigit() for a in ans):
                    continue
            rows.append({
                "qid":      row["qid"],
                "question": row["question"],
                "answer":   row["answer"],
                "traj_id":  row["traj_id"],
            })
    return rows


# ── Gate / frontier run ───────────────────────────────────────────────────────

def run_gate(mc_n: int = 100, sc_n: int = 50, conditions: list = None,
             out_path: Path = None, seed: int = 42):
    if conditions is None:
        conditions = ["blind", "window-10", "summary-80", "summary-200", "full"]

    RESULTS.mkdir(exist_ok=True)
    rng = random.Random(seed)

    # Load QA
    mc_qa = load_qa(MC_CSV)
    sc_qa = load_qa(SC_CSV)

    # Filter to trajectories we have
    mc_qa = [q for q in mc_qa if _find_traj(q["traj_id"]) is not None]
    sc_qa = [q for q in sc_qa if _find_traj(q["traj_id"]) is not None]

    print(f"Multi-clue QA with traj available: {len(mc_qa)}")
    print(f"Single-clue QA with traj available: {len(sc_qa)}")

    # Use all available questions (dataset cap: only 62/219 traj_ids shipped on HuggingFace).
    # mc_n / sc_n are upper bounds; if fewer are available, run all.
    mc_sample = rng.sample(mc_qa, min(mc_n, len(mc_qa)))
    sc_sample = rng.sample(sc_qa, min(sc_n, len(sc_qa)))

    n_traj_total = 219
    n_traj_avail = len({q["traj_id"] for q in mc_qa + sc_qa})
    print(f"\nDataset coverage: {n_traj_avail}/{n_traj_total} traj_ids available in metadata.tar")
    print(f"  (157 traj_ids referenced in QA CSVs are absent from HuggingFace release)")
    print(f"  This caps frontier n but does not bias gate — missing trajs are not selected out.")

    # ── Token length survey ────────────────────────────────────────────────────
    print("\n── Token length survey (sample of 20 trajectories) ──────────────")
    from transformers import AutoTokenizer
    tok_survey = AutoTokenizer.from_pretrained(REASONING_MODEL_ID)
    seen_ids = set()
    token_lengths = []
    for q in (mc_sample + sc_sample):
        if q["traj_id"] in seen_ids:
            continue
        seen_ids.add(q["traj_id"])
        txt = load_traj_text(q["traj_id"])
        if txt:
            n_tok = count_tokens(tok_survey, txt)
            token_lengths.append(n_tok)
        if len(token_lengths) >= 20:
            break

    if token_lengths:
        print(f"  n={len(token_lengths)} trajectories sampled")
        print(f"  min={min(token_lengths):,}  max={max(token_lengths):,}  "
              f"mean={sum(token_lengths)//len(token_lengths):,} tokens")
        max_ctx = tok_survey.model_max_length
        print(f"  Model max context: {max_ctx:,} tokens")
        n_over = sum(1 for t in token_lengths if t > 32768)
        print(f"  Trajectories > 32K tokens: {n_over}/{len(token_lengths)}")
        n_over128 = sum(1 for t in token_lengths if t > 131072)
        print(f"  Trajectories > 128K tokens: {n_over128}/{len(token_lengths)}")
        del tok_survey

    # ── Load LLM ──────────────────────────────────────────────────────────────
    model, tok = load_llm()
    summary_fn = make_summary_fn(model, tok)

    # ── Run conditions ────────────────────────────────────────────────────────
    def run_split(qa_list: list[dict], split_name: str) -> list[dict]:
        records = []
        for i, q in enumerate(qa_list):
            traj_text = load_traj_text(q["traj_id"])
            if traj_text is None:
                print(f"  SKIP {q['qid']}: traj not found")
                continue
            steps = get_steps(traj_text)
            gold = parse_answer_list(q["answer"])
            n_tokens = count_tokens(tok, traj_text)
            top_rec = detect_top_receptacles(traj_text)
            salient = is_salient(gold, top_rec)
            ev_dist = evidence_distance(steps, gold)

            rec = {
                "qid":              q["qid"],
                "traj_id":          q["traj_id"],
                "question":         q["question"],
                "gold":             gold,
                "n_steps":          len(steps),
                "n_tokens_full":    n_tokens,
                "top_receptacles":  top_rec,
                "is_salient":       salient,
                "evidence_distance": ev_dist,
                "split":            split_name,
                "conditions":       {},
            }

            for cond in conditions:
                t0 = time.perf_counter()
                raw, final = answer_question(model, tok, steps, q["question"],
                                             cond, summary_fn)
                elapsed = time.perf_counter() - t0
                em = exact_match(final, gold)
                pm = partial_match(final, gold)
                jd = llm_judge(model, tok, final, gold)
                rec["conditions"][cond] = {
                    "pred":          final,
                    "exact_match":   em,
                    "partial_match": pm,
                    "llm_judge":     jd,
                    "elapsed_s":     round(elapsed, 2),
                }
                sal = "SAL" if salient else "   "
                dist_tag = ev_dist["distance_bin"][:4].upper()
                print(f"  [{split_name}] {i+1:3d}/{len(qa_list)} "
                      f"[{cond:12s}] {sal} [{dist_tag}] "
                      f"pred={final!r:25s} gold={gold!r:25s} "
                      f"em={em} pm={pm} j={jd}")
            records.append(rec)
        return records

    print("\n── Multi-clue (NsiEH) — headline split ─────────────────────────")
    mc_records = run_split(mc_sample, "multi_clue")

    print("\n── Single-clue (NiEH) — secondary split ─────────────────────────")
    sc_records = run_split(sc_sample, "single_clue")

    # ── Statistics ─────────────────────────────────────────────────────────────
    def _acc(recs, cond, metric="llm_judge"):
        vals = [r["conditions"][cond][metric]
                for r in recs if cond in r["conditions"]]
        return (sum(vals) / len(vals), len(vals)) if vals else (0.0, 0)

    print("\n" + "=" * 100)
    print("GATE RESULTS")
    print("=" * 100)

    for split_name, records in [("MULTI-CLUE (headline)", mc_records),
                                  ("SINGLE-CLUE (secondary)", sc_records)]:
        ns_recs  = [r for r in records if not r["is_salient"]]
        s_recs   = [r for r in records if     r["is_salient"]]
        near_recs = [r for r in ns_recs if r["evidence_distance"]["distance_bin"] == "near"]
        mid_recs  = [r for r in ns_recs if r["evidence_distance"]["distance_bin"] == "mid"]
        far_recs  = [r for r in ns_recs if r["evidence_distance"]["distance_bin"] == "far"]

        print(f"\n{split_name}")
        print(f"  n={len(records)} total  salient={len(s_recs)}  non-salient={len(ns_recs)}")
        print(f"  Evidence distance (non-salient): near(≤10)={len(near_recs)} "
              f"mid(11-30)={len(mid_recs)} far(>30)={len(far_recs)}")

        hdr = f"\n  {'subset':<30} " + " ".join(f"{c:>13}" for c in conditions)
        print(hdr)
        print("  " + "-" * (30 + 14 * len(conditions)))

        for label, recs in [
            ("ALL", records),
            ("  salient", s_recs),
            ("  non-salient ←KEY", ns_recs),
            ("    ns / near (≤10 steps)", near_recs),
            ("    ns / mid  (11-30 steps)", mid_recs),
            ("    ns / far  (>30 steps)", far_recs),
        ]:
            row = f"  {label:<30}"
            for cond in conditions:
                acc, n = _acc(recs, cond, "llm_judge")
                row += f"  {acc:.2f}({n:3d})"
            print(row)

        # Distance-resolved gap table (full − window-10, full − summary-80)
        print(f"\n  Distance-resolved gaps (full − condition, non-salient LLM-judge):")
        gap_hdr = f"    {'bin':<20} {'full':>6} {'full−win10':>10} {'full−sum80':>10} n"
        print(gap_hdr)
        for bin_label, bin_recs in [
            ("near ≤10", near_recs),
            ("mid 11-30", mid_recs),
            ("far >30", far_recs),
            ("ALL ns", ns_recs),
        ]:
            full_acc, n = _acc(bin_recs, "full", "llm_judge")
            win_acc, _  = _acc(bin_recs, "window-10", "llm_judge")
            s80_acc, _  = _acc(bin_recs, "summary-80", "llm_judge")
            print(f"    {bin_label:<20} {full_acc:6.2f} {full_acc-win_acc:10.2f} "
                  f"{full_acc-s80_acc:10.2f} {n}")

    # ── Per-trajectory dispersion guard (multi-clue non-salient only) ─────────
    mc_ns_all = [r for r in mc_records if not r["is_salient"]]
    if mc_ns_all:
        print(f"\n  Dispersion guard — full−window-10 gap, per trajectory (multi-clue non-salient):")
        traj_gaps: dict[str, dict] = {}
        for r in mc_ns_all:
            tid = r["traj_id"]
            if tid not in traj_gaps:
                traj_gaps[tid] = {"full": [], "window-10": [], "summary-80": []}
            for cond in ("full", "window-10", "summary-80"):
                if cond in r["conditions"]:
                    traj_gaps[tid][cond].append(r["conditions"][cond]["llm_judge"])

        traj_win_gaps, traj_s80_gaps = [], []
        for tid, vals in traj_gaps.items():
            if vals["full"] and vals["window-10"]:
                g = sum(vals["full"]) / len(vals["full"]) - sum(vals["window-10"]) / len(vals["window-10"])
                traj_win_gaps.append((tid, g, len(vals["full"])))
            if vals["full"] and vals["summary-80"]:
                g = sum(vals["full"]) / len(vals["full"]) - sum(vals["summary-80"]) / len(vals["summary-80"])
                traj_s80_gaps.append((tid, g, len(vals["full"])))

        traj_win_gaps.sort(key=lambda x: -x[1])
        traj_s80_gaps.sort(key=lambda x: -x[1])

        n_pos_win = sum(1 for _, g, _ in traj_win_gaps if g > 0)
        n_pos_s80 = sum(1 for _, g, _ in traj_s80_gaps if g > 0)
        top3_win = traj_win_gaps[:3]
        top3_s80 = traj_s80_gaps[:3]

        # What fraction of total gap is carried by top-1 and top-3 trajectories?
        total_win = sum(g * n for _, g, n in traj_win_gaps if g > 0) or 1
        total_s80 = sum(g * n for _, g, n in traj_s80_gaps if g > 0) or 1
        top1_win_share = traj_win_gaps[0][1] * traj_win_gaps[0][2] / total_win if traj_win_gaps else 0
        top3_win_share = sum(g * n for _, g, n in traj_win_gaps[:3] if g > 0) / total_win
        top1_s80_share = traj_s80_gaps[0][1] * traj_s80_gaps[0][2] / total_s80 if traj_s80_gaps else 0
        top3_s80_share = sum(g * n for _, g, n in traj_s80_gaps[:3] if g > 0) / total_s80

        print(f"    full−win10: {n_pos_win}/{len(traj_win_gaps)} trajs show positive gap")
        print(f"      top-1 carries {top1_win_share:.0%} of total gap  "
              f"top-3 carries {top3_win_share:.0%}")
        print(f"      top-3 trajs: " + ", ".join(f"{t}(gap={g:+.2f},n={n})" for t,g,n in top3_win))
        print(f"    full−sum80: {n_pos_s80}/{len(traj_s80_gaps)} trajs show positive gap")
        print(f"      top-1 carries {top1_s80_share:.0%} of total gap  "
              f"top-3 carries {top3_s80_share:.0%}")
        print(f"      top-3 trajs: " + ", ".join(f"{t}(gap={g:+.2f},n={n})" for t,g,n in top3_s80))
        if top1_win_share > 0.5 or top1_s80_share > 0.5:
            print("    WARNING: single trajectory carries >50% of gap — headline may not generalise.")
        elif top3_win_share > 0.8 or top3_s80_share > 0.8:
            print("    CAUTION: top-3 trajectories carry >80% of gap — moderate concentration.")
        else:
            print("    OK: gap is spread across trajectories.")

    # ── Stop-condition check ───────────────────────────────────────────────────
    mc_ns = [r for r in mc_records if not r["is_salient"]]
    full_acc, _ = _acc(mc_ns, "full", "llm_judge")
    blind_acc, _ = _acc(mc_ns, "blind", "llm_judge")
    sum80_acc, _ = _acc(mc_ns, "summary-80", "llm_judge")

    sc1 = "PASS" if full_acc > blind_acc + 0.05 else (
          f"FAIL (full={full_acc:.2f}, blind={blind_acc:.2f})")
    sc2 = "PASS" if (full_acc - sum80_acc) > 0.05 else (
          f"FAIL (full={full_acc:.2f}, sum80={sum80_acc:.2f}, "
          f"gap={full_acc - sum80_acc:.2f})")

    print(f"\nStop-condition checks (multi-clue non-salient):")
    print(f"  1. Full clearly above blind floor: {sc1}")
    print(f"  2. Visible full→summary-80 drop:   {sc2}")

    if "PASS" in sc1 and "PASS" in sc2:
        print("\nBOTH PASS → proceed to full frontier.")
    else:
        print("\nNOT BOTH PASS → stop, report to user.")

    # ── Save ──────────────────────────────────────────────────────────────────
    all_records = mc_records + sc_records
    traj_tok_dist = {
        "n_sampled": len(token_lengths),
        "min": min(token_lengths) if token_lengths else None,
        "max": max(token_lengths) if token_lengths else None,
        "mean": sum(token_lengths) // len(token_lengths) if token_lengths else None,
    }
    device = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    dataset_coverage = {
        "traj_ids_in_qa_csvs":      219,
        "traj_ids_in_metadata_tar": n_traj_avail,
        "traj_ids_missing":         219 - n_traj_avail,
        "note": (
            "Only 62 of 219 traj_ids referenced in QA CSVs are present in the "
            "HuggingFace metadata.tar release (as of 2026-06-22). The 157 missing "
            "traj_ids are absent from the public release; they are not filtered out "
            "by any accuracy criterion, so coverage cap does not bias gate direction."
        ),
    }

    prov = stamp(
        script="frontier_infinithor.py",
        model="qwen7b",
        device=device.lower().replace(" ", "_"),
        n=len(all_records),
        args=argparse.Namespace(
            reasoning_model=REASONING_MODEL_ID,
            text_source="simulator_oracle_ground_truth",
            oracle_guard="gt_steps_gt_img_idx_never_fed_as_input",
            conditions=conditions,
            mc_n=len(mc_records),
            sc_n=len(sc_records),
            seed=seed,
            traj_token_distribution=traj_tok_dist,
            dataset_coverage=dataset_coverage,
        ),
    )

    out = {
        "metadata": {
            "reasoning_model":   REASONING_MODEL_ID,
            "text_source":       "simulator_oracle_ground_truth",
            "oracle_guard":      "gt_steps and gt_img_idx never fed as input",
            "conditions":        conditions,
            "mc_n":              len(mc_records),
            "sc_n":              len(sc_records),
            "seed":              seed,
            "traj_token_distribution": traj_tok_dist,
            "dataset_coverage":  dataset_coverage,
            "timestamp":         datetime.now().isoformat(),
        },
        "stop_conditions": {
            "sc1_full_above_blind": sc1,
            "sc2_full_to_summary_drop": sc2,
        },
        "records": all_records,
        "_provenance": prov,
    }
    if out_path:
        _save_json(out_path, out)
        print(f"\n  Results saved → {out_path}")

    del model, tok
    gc.collect()
    torch.cuda.empty_cache()
    print("\nStopped after gate. Do not stage or commit.")
    return out


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Infini-THOR NiEH gate + frontier")
    ap.add_argument("--gate", action="store_true",
                    help="Run gate (all available questions, up to mc-n/sc-n cap)")
    ap.add_argument("--frontier", action="store_true",
                    help="Full frontier (all usable questions)")
    ap.add_argument("--mc-n", type=int, default=999)
    ap.add_argument("--sc-n", type=int, default=999)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="results/frontier_infinithor_qwen7b.json")
    args = ap.parse_args()

    if args.gate:
        # Lean gate: only the three conditions that decide the gate.
        # window-10, summary-200, single-clue are frontier detail — run only after gate passes.
        run_gate(
            mc_n=args.mc_n, sc_n=args.sc_n,
            conditions=["blind", "summary-80", "full"],
            out_path=Path(args.out), seed=args.seed,
        )
    else:
        print("Use --gate or --frontier.")
        ap.print_help()


if __name__ == "__main__":
    main()
