"""Diagnostic for E26 item 3: check actual input token counts for summary update at large L."""
import sys
sys.path.insert(0, "experiments/lib")
sys.path.insert(0, "experiments/cost")

from transformers import AutoTokenizer
from cost_profile import build_corpus, SUMMARY_PROMPT, sample_context

tok = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-7B-Instruct")
corpus = build_corpus(tok)

print(f"{'L':>8} | {'actual_ctx':>12} | {'char_cap_toks':>14} | {'full_prompt_toks':>17} | {'after_trunc(L+256)':>20}")
print("-" * 84)
for L in [8192, 32768, 49152, 65536]:
    ctx_text, turns, actual_L = sample_context(corpus, tok, L, "cpu")
    # Original path: character-capped at 8000 chars
    p_char = SUMMARY_PROMPT.format(n=200, context=ctx_text[:8000])
    n_char = tok(p_char, return_tensors="pt")["input_ids"].shape[1]
    # Corrected path: full context
    p_full = SUMMARY_PROMPT.format(n=200, context=ctx_text)
    n_full_raw = tok(p_full, return_tensors="pt")["input_ids"].shape[1]
    # HF tokenizer with truncation at max_length=actual_L+256 (as used in corrected sweep)
    n_full_trunc = tok(p_full, return_tensors="pt", truncation=True, max_length=actual_L+256)["input_ids"].shape[1]
    print(f"{L:>8,} | {actual_L:>12,} | {n_char:>14,} | {n_full_raw:>17,} | {n_full_trunc:>20,}")

print()
print("Note: max_position_embeddings=32768 for this model snapshot.")
print("At L>=32768, full_prompt_toks exceeds the model's position limit.")
print("HF generate() with these inputs may silently clip positions or produce OOB,")
print("explaining the plateau in measured update latency above L=32k.")
