"""
GeoLife micro-gate audit harness.
Conditions: blind | window-5 | summary-80 | summary-200 | full
Judge: exact-match (case-insensitive substring) + Qwen2.5-7B judge
Omission audit: for gap cases (full=1, summary-80=0), check if gold is absent from summary
"""
import json, time, sys, re
from pathlib import Path
from collections import defaultdict

QUESTIONS_FILE = "/tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/geolife_questions.json"
OUT_FILE = "/tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/geolife_audit_results.json"

WINDOW_K = 5  # last K stops from timeline text

# ── model loading ─────────────────────────────────────────────────────────────

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"
print("Loading Qwen2.5-7B-Instruct...", flush=True)
tok = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID, dtype=torch.float16, device_map="auto"
)
model.eval()
print("Model loaded.", flush=True)

# ── inference helper ──────────────────────────────────────────────────────────

def chat(system, user_msg, max_new_tokens=80):
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user_msg}]
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tok(text, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=max_new_tokens,
                             do_sample=False, temperature=None, top_p=None)
    gen = out[0][inputs["input_ids"].shape[1]:]
    return tok.decode(gen, skip_special_tokens=True).strip()

# ── context builders ──────────────────────────────────────────────────────────

def build_window(full_ctx, k=5):
    """Return last k stops from the timeline text."""
    lines = [l for l in full_ctx.strip().splitlines() if l.strip()]
    return "\n".join(lines[-k:])

def build_summary(full_ctx, target_tokens):
    prompt = (f"Summarize this weekly location timeline in approximately {target_tokens} tokens. "
              f"Include all named places visited and when, but be concise.\n\n"
              f"Timeline:\n{full_ctx}")
    return chat("You are a concise summarizer.", prompt, max_new_tokens=target_tokens + 30)

# ── answer generation ─────────────────────────────────────────────────────────

ANSWER_SYSTEM = ("You are a precise factual assistant. Answer the question using only "
                 "the provided timeline. Give ONLY the place name or transport mode as "
                 "your answer — no explanation, no punctuation, no quotes. "
                 "If you cannot find the answer, say: CANNOT DETERMINE")

def generate_answer(question, context):
    if context:
        user_msg = f"Timeline:\n{context}\n\nQuestion: {question}"
    else:
        user_msg = f"Question (no context provided): {question}"
    return chat(ANSWER_SYSTEM, user_msg, max_new_tokens=30)

# ── judge ─────────────────────────────────────────────────────────────────────

JUDGE_SYSTEM = ("You are a strict factual judge. The question asks about a specific "
                "location or transport mode. Given the gold answer and a predicted answer, "
                "reply with exactly YES if the prediction correctly identifies the gold "
                "answer (allowing minor transliteration variants or partial matches for "
                "Chinese names), or NO otherwise. Reply only: YES or NO")

def exact_match(pred, gold):
    return gold.lower().strip() in pred.lower() or pred.lower().strip() in gold.lower()

def llm_judge(question, gold, pred):
    user_msg = f"Question: {question}\nGold answer: {gold}\nPredicted answer: {pred}"
    resp = chat(JUDGE_SYSTEM, user_msg, max_new_tokens=5)
    return "yes" in resp.lower()

def judge(question, gold, pred):
    em = exact_match(pred, gold)
    if "CANNOT DETERMINE" in pred.upper():
        return {"exact": False, "judge": False, "judge_called": False, "correct": False}
    lj = llm_judge(question, gold, pred)
    return {"exact": em, "judge": lj, "judge_called": True, "correct": em or lj}

# ── omission audit ────────────────────────────────────────────────────────────

OMISSION_SYSTEM = ("You are a careful text analyst. Given a summary and a gold answer, "
                   "reply YES if the gold answer (or a clear synonym/transliteration) "
                   "appears anywhere in the summary, NO otherwise. Reply only: YES or NO")

def check_gold_in_summary(gold, summary):
    if gold.lower() in summary.lower():
        return True
    user_msg = f"Summary:\n{summary}\n\nGold answer: {gold}\n\nIs the gold answer present in the summary?"
    resp = chat(OMISSION_SYSTEM, user_msg, max_new_tokens=5)
    return "yes" in resp.lower()

# ── main audit loop ───────────────────────────────────────────────────────────

def main():
    with open(QUESTIONS_FILE) as f:
        questions = json.load(f)
    print(f"Loaded {len(questions)} questions", flush=True)

    # Pre-generate summaries per unique week (cache)
    print("\nPre-generating summaries per unique week...", flush=True)
    week_summaries_80 = {}
    week_summaries_200 = {}
    unique_weeks = {(q["user_id"], q["week_key"]): q["full_context"]
                    for q in questions}

    for (uid, wk), ctx in unique_weeks.items():
        key = f"{uid}_{wk}"
        print(f"  Summarizing {key} ({len(ctx)} chars)...", flush=True)
        week_summaries_80[key] = build_summary(ctx, 80)
        week_summaries_200[key] = build_summary(ctx, 200)

    print(f"\nRunning audit on {len(questions)} questions × 5 conditions...", flush=True)
    results = []
    n_done = 0

    for q in questions:
        uid, wk = q["user_id"], q["week_key"]
        week_key = f"{uid}_{wk}"
        full_ctx = q["full_context"]
        question = q["question"]
        gold = q["gold"]

        s80 = week_summaries_80[week_key]
        s200 = week_summaries_200[week_key]
        window_ctx = build_window(full_ctx, k=WINDOW_K)

        conditions = {}
        for cond_name, ctx in [("blind", None), ("window-5", window_ctx),
                                ("summary-80", s80), ("summary-200", s200),
                                ("full", full_ctx)]:
            pred = generate_answer(question, ctx)
            j = judge(question, gold, pred)
            conditions[cond_name] = {"pred": pred, **j}

        # Omission audit for gap cases: full=correct, summary-80=incorrect
        omission = None
        if conditions["full"]["correct"] and not conditions["summary-80"]["correct"]:
            gold_in_s80 = check_gold_in_summary(gold, s80)
            omission = "compression-omission" if not gold_in_s80 else "reasoning-failure"

        record = {
            "q_uid": q["q_uid"],
            "user_id": uid,
            "week_key": wk,
            "template": q["template"],
            "question": question,
            "gold": gold,
            "anchor": q["anchor"],
            "evidence_distance_from_end": q["evidence_distance_from_end"],
            "n_stops_in_week": q["n_stops_in_week"],
            "token_count": len(full_ctx) // 4,
            "summary_80": s80,
            "summary_200": s200,
            "conditions": conditions,
            "omission": omission,
        }
        results.append(record)
        n_done += 1

        if n_done % 10 == 0 or n_done == 1:
            # Running stats
            def acc(cond): return sum(r["conditions"][cond]["correct"] for r in results) / len(results)
            print(f"  [{n_done}/{len(questions)}] full={acc('full'):.3f} s80={acc('summary-80'):.3f} blind={acc('blind'):.3f}", flush=True)

        # Save checkpoint every 20 questions
        if n_done % 20 == 0:
            with open(OUT_FILE, "w") as f:
                json.dump(results, f, indent=2)

    # Final save
    with open(OUT_FILE, "w") as f:
        json.dump(results, f, indent=2)

    # ── Report ────────────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("GEOLIFE MICRO-GATE RESULTS")
    print("="*60)
    n = len(results)

    conds = ["blind", "window-5", "summary-80", "summary-200", "full"]
    for c in conds:
        correct = sum(r["conditions"][c]["correct"] for r in results)
        print(f"  {c:12s}: {correct/n:.3f} ({correct}/{n})")

    # Gap
    full_correct = [r for r in results if r["conditions"]["full"]["correct"]]
    s80_correct = [r for r in results if r["conditions"]["summary-80"]["correct"]]
    full_acc = len(full_correct) / n
    s80_acc = len(s80_correct) / n
    gap = full_acc - s80_acc
    print(f"\n  full - summary-80 gap: {gap:+.3f}")

    # McNemar test
    a = sum(1 for r in results if r["conditions"]["full"]["correct"] and not r["conditions"]["summary-80"]["correct"])
    b = sum(1 for r in results if not r["conditions"]["full"]["correct"] and r["conditions"]["summary-80"]["correct"])
    print(f"  Gap cases (full=1,s80=0): {a}, reverse (full=0,s80=1): {b}")
    if (a + b) > 0:
        from scipy.stats import binom_test
        try:
            p = binom_test(a, a+b, 0.5)
        except:
            p = None
        if p is not None:
            print(f"  McNemar p-value: {p:.4f}")

    # Omission audit
    gap_cases = [r for r in results if r["conditions"]["full"]["correct"]
                 and not r["conditions"]["summary-80"]["correct"]]
    omission_cases = [r for r in gap_cases if r["omission"] == "compression-omission"]
    reasoning_cases = [r for r in gap_cases if r["omission"] == "reasoning-failure"]
    print(f"\n  Gap cases analyzed: {len(gap_cases)}")
    if gap_cases:
        print(f"  Compression-omission: {len(omission_cases)}/{len(gap_cases)} ({100*len(omission_cases)//len(gap_cases)}%)")
        print(f"  Reasoning failure:    {len(reasoning_cases)}/{len(gap_cases)} ({100*len(reasoning_cases)//len(gap_cases)}%)")

    # Token length
    toks = [r["token_count"] for r in results]
    print(f"\n  Timeline token lengths: min={min(toks)}, median={sorted(toks)[n//2]}, max={max(toks)}")

    # Template breakdown
    for tmpl in ["T1_before", "T3_after", "T4_mode"]:
        sub = [r for r in results if r["template"] == tmpl]
        if not sub:
            continue
        full_a = sum(r["conditions"]["full"]["correct"] for r in sub) / len(sub)
        s80_a = sum(r["conditions"]["summary-80"]["correct"] for r in sub) / len(sub)
        print(f"\n  {tmpl} (n={len(sub)}): full={full_a:.3f}, s80={s80_a:.3f}, gap={full_a-s80_a:+.3f}")

    print(f"\nFull results saved to {OUT_FILE}")

if __name__ == "__main__":
    main()
