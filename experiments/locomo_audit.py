"""
LoCoMo Audit — Representation Omission and Evidence Distance
=============================================================
Augments the existing frontier_locomo_qwen7b_perquestion.json with:

  1. Evidence distance: turns and tokens from the evidence turn to end of history.
  2. Summary-omission audit: for each representation (full, summary-80, summary-200),
     whether the gold answer is PRESENT (exact normalized match, then LLM judge for misses).

Separates two failure modes:
  - Compression-omission: gold fact absent from summary → compression discarded it.
  - Model failure: gold fact present in summary but model answered wrong.

Reports:
  A. Omission table: for summary-condition misses, fraction where gold was absent.
  B. Full-vs-summary accuracy gaps by evidence distance (near/mid/far in turns).
     Plus dispersion guard: is gap concentrated in a few questions?
  C. Context-length and evidence-distance distributions.
  D. Ceiling: total cat=1 questions available in locomo10.json.

Oracle guard: gold answer checked against representations built from conversation text.
Evidence location resolved from LoCoMo dia_id annotations (D{session}:{turn});
method stamped in provenance as "locomo_dia_id_annotation".

Usage:
    CUDA_VISIBLE_DEVICES=1 python experiments/locomo_audit.py
"""

import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import torch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "experiments"))
from _provenance import stamp

DATA_PATH      = ROOT / "data"  / "locomo" / "locomo10.json"
PERQ_PATH      = ROOT / "results" / "frontier_locomo_qwen7b_perquestion.json"
SUM80_PATH     = ROOT / "results" / "locomo_summaries_80.json"
SUM200_PATH    = ROOT / "results" / "locomo_summaries_200.json"
OUT_PATH       = ROOT / "results" / "locomo_audit_qwen7b.json"
INDEX_PATH     = ROOT / "results" / "INDEX.md"

MODEL_ID  = "Qwen/Qwen2.5-7B-Instruct"
DEVICE    = "cuda:0"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().strip())


def _save_json(path, obj):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    tmp.replace(path)


# ── Conversation loading ──────────────────────────────────────────────────────

def load_conversations(data_path: Path) -> dict:
    """Returns conv_id → {sessions, dates, speaker_a, speaker_b, all_turns, full_text}."""
    raw = json.loads(data_path.read_text())
    convs = {}
    for item in raw:
        conv_id = item["sample_id"]
        c = item["conversation"]
        sessions, dates, all_turns = [], [], []
        i = 1
        while f"session_{i}" in c:
            turns = c[f"session_{i}"]
            sessions.append(turns)
            dates.append(c.get(f"session_{i}_date_time", ""))
            for t in turns:
                all_turns.append(t)
            i += 1
        # Build full text (same format as frontier_locomo.py)
        lines = []
        for si, (sess, date) in enumerate(zip(sessions, dates)):
            header = f"[Session {si+1}" + (f" — {date}]" if date else "]")
            lines.append(header)
            for t in sess:
                lines.append(f"{t['speaker']}: {t['text']}")
            lines.append("")
        convs[conv_id] = {
            "sessions": sessions,
            "dates": dates,
            "speaker_a": c.get("speaker_a", "A"),
            "speaker_b": c.get("speaker_b", "B"),
            "all_turns": all_turns,
            "full_text": "\n".join(lines).strip(),
        }
    return convs


def resolve_evidence_turns(evidence_list: list[str], all_turns: list[dict]) -> list[int]:
    """Map dia_id strings like 'D2:8' to 0-based absolute turn indices."""
    dia_to_idx = {t["dia_id"]: i for i, t in enumerate(all_turns)}
    indices = []
    for ev in evidence_list:
        if ev in dia_to_idx:
            indices.append(dia_to_idx[ev])
    return indices


def evidence_distance(ev_indices: list[int], total_turns: int) -> dict:
    if not ev_indices:
        return {"method": "locomo_dia_id_annotation", "found": False,
                "last_ev_turn_idx": -1, "turns_from_end": -1, "distance_bin": "not_found"}
    last = max(ev_indices)
    dist = total_turns - 1 - last
    if dist <= 5:
        bin_ = "near"
    elif dist <= 20:
        bin_ = "mid"
    else:
        bin_ = "far"
    return {"method": "locomo_dia_id_annotation", "found": True,
            "last_ev_turn_idx": last, "turns_from_end": dist, "distance_bin": bin_}


def token_evidence_distance(ev_indices: list[int], all_turns: list[dict],
                             full_text: str, tok) -> dict:
    """Compute evidence distance in tokens by finding the evidence sentence in full_text."""
    if not ev_indices:
        return {"ev_token_idx": -1, "tokens_from_end": -1,
                "total_tokens": len(tok.encode(full_text, add_special_tokens=False))}
    total_tok = len(tok.encode(full_text, add_special_tokens=False))
    last_ev_turn = all_turns[max(ev_indices)]
    # Find the position of the evidence sentence in the full_text
    ev_text = f"{last_ev_turn['speaker']}: {last_ev_turn['text']}"
    idx = full_text.find(ev_text)
    if idx < 0:
        return {"ev_token_idx": -1, "tokens_from_end": -1, "total_tokens": total_tok}
    ev_tok_idx = len(tok.encode(full_text[:idx + len(ev_text)], add_special_tokens=False))
    return {"ev_token_idx": ev_tok_idx, "tokens_from_end": total_tok - ev_tok_idx,
            "total_tokens": total_tok}


# ── LLM ──────────────────────────────────────────────────────────────────────

def load_llm():
    from transformers import AutoTokenizer, AutoModelForCausalLM
    print(f"Loading {MODEL_ID} ...")
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, dtype=torch.float16, device_map=DEVICE)
    model.eval()
    return model, tok


def _run(model, tok, prompt: str, max_new: int = 8) -> str:
    fmt = tok.apply_chat_template([{"role": "user", "content": prompt}],
                                   tokenize=False, add_generation_prompt=True)
    inp = tok(fmt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**inp, max_new_tokens=max_new, do_sample=False,
                              pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][inp["input_ids"].shape[1]:], skip_special_tokens=True).strip()


PRESENCE_PROMPT = (
    "Does the following text contain the answer '{gold}'?\n"
    "Text: {text}\n\n"
    "Answer YES if the text explicitly mentions or clearly implies '{gold}'. "
    "Answer NO otherwise.\nReply with only YES or NO."
)


def check_gold_presence(text: str, gold: str, model, tok) -> dict:
    """Check whether gold answer is present in text. Returns exact and judge booleans."""
    # Exact normalized substring match
    exact = _normalize(gold) in _normalize(text)
    if exact:
        return {"exact": True, "judge": True, "judge_called": False}
    # LLM judge only on misses
    snippet = text[:3000]
    prompt = PRESENCE_PROMPT.format(gold=gold, text=snippet)
    resp = _run(model, tok, prompt, max_new=4)
    judge = resp.upper().startswith("YES")
    return {"exact": False, "judge": judge, "judge_called": True}


# ── Main audit ────────────────────────────────────────────────────────────────

def run_audit():
    # Load existing perquestion results
    perq = json.load(PERQ_PATH.open())
    print(f"Loaded {len(perq)} perquestion records.")

    # Load conversations and summaries
    convs   = load_conversations(DATA_PATH)
    sum80   = json.load(SUM80_PATH.open())    # conv_id → summary text
    sum200  = json.load(SUM200_PATH.open())

    # Total cat=1 ceiling
    raw_all = json.loads(DATA_PATH.read_text())
    total_cat1 = sum(1 for c in raw_all for q in c["qa"] if q["category"] == 1)
    print(f"Ceiling: {total_cat1} cat=1 questions total in locomo10.json")

    # Load tokenizer for token-distance
    from transformers import AutoTokenizer
    tok_survey = AutoTokenizer.from_pretrained(MODEL_ID)

    # Pre-compute full-context token lengths per conv
    full_tok_len = {cid: len(tok_survey.encode(cv["full_text"], add_special_tokens=False))
                    for cid, cv in convs.items()}

    # Augment each record with distance info (no LLM needed yet)
    print("Computing evidence distances ...")
    for rec in perq:
        cid = rec["conv_id"]
        cv  = convs[cid]
        ev_indices = resolve_evidence_turns(rec["evidence"], cv["all_turns"])
        turn_dist  = evidence_distance(ev_indices, len(cv["all_turns"]))
        tok_dist   = token_evidence_distance(ev_indices, cv["all_turns"],
                                              cv["full_text"], tok_survey)
        rec["evidence_distance_turns"] = turn_dist
        rec["evidence_distance_tokens"] = tok_dist
        rec["full_context_tokens"]     = full_tok_len[cid]

    del tok_survey

    # Load LLM for omission audit
    model, tok = load_llm()

    print("Running omission audit ...")
    judge_calls = 0
    for i, rec in enumerate(perq):
        cid   = rec["conv_id"]
        cv    = convs[cid]
        gold  = rec["gold"]
        full_text = cv["full_text"]
        s80_text  = sum80.get(cid, "")
        s200_text = sum200.get(cid, "")

        presence = {}
        for rep_name, text in [("full", full_text),
                                ("summary-80", s80_text),
                                ("summary-200", s200_text)]:
            res = check_gold_presence(text, gold, model, tok)
            presence[rep_name] = res
            if res["judge_called"]:
                judge_calls += 1

        rec["gold_presence"] = presence

        dist_bin = rec["evidence_distance_turns"].get("distance_bin", "?")
        s80_correct = rec["conditions"].get("summary-80", {}).get("correct", -1)
        full_correct = rec["conditions"].get("full", {}).get("correct", -1)
        s80_present  = presence["summary-80"]["judge"]
        print(f"  {i+1:2d}/{len(perq)} [{dist_bin:8s}] "
              f"full={full_correct} s80={s80_correct} "
              f"gold-in-s80={s80_present} gold={repr(gold[:30])}")

    print(f"  LLM judge calls for omission: {judge_calls}")

    import gc
    del model, tok
    gc.collect()
    torch.cuda.empty_cache()

    # ── Reporting ─────────────────────────────────────────────────────────────

    conditions_of_interest = ["blind", "window-10", "full", "summary-80", "summary-200"]

    def acc(recs, cond):
        vals = [r["conditions"][cond]["correct"] for r in recs if cond in r["conditions"]]
        return (sum(vals) / len(vals), len(vals)) if vals else (0.0, 0)

    print("\n" + "=" * 90)
    print("LOCOMO AUDIT RESULTS")
    print("=" * 90)

    # D: Ceiling
    print(f"\nD. Ceiling: {total_cat1} cat=1 questions in locomo10.json  "
          f"(current audit n={len(perq)})")

    # C: Context length and evidence distance distributions
    print("\nC. Context-length distribution (full history, tokens):")
    tok_lens = [r["full_context_tokens"] for r in perq]
    print(f"   min={min(tok_lens):,}  max={max(tok_lens):,}  "
          f"mean={sum(tok_lens)//len(tok_lens):,}")

    print("\n   Evidence distance distribution (turns from end of history):")
    bins = {"near": [], "mid": [], "far": [], "not_found": []}
    for r in perq:
        b = r["evidence_distance_turns"].get("distance_bin", "not_found")
        bins[b].append(r["evidence_distance_turns"].get("turns_from_end", -1))
    for b, vals in bins.items():
        if vals:
            avg = sum(v for v in vals if v >= 0) / max(1, sum(1 for v in vals if v >= 0))
            print(f"   {b:10s}: n={len(vals):3d}  avg_turns_from_end={avg:.1f}")

    print("\n   Evidence distance distribution (tokens from end):")
    tok_dists = [(r["evidence_distance_tokens"].get("tokens_from_end", -1),
                  r["evidence_distance_turns"].get("distance_bin", "?")) for r in perq]
    for b in ["near", "mid", "far"]:
        vals = [d for d, bin_ in tok_dists if bin_ == b and d >= 0]
        if vals:
            print(f"   {b:10s}: n={len(vals):3d}  "
                  f"avg_tok_from_end={sum(vals)//len(vals):,}  "
                  f"max={max(vals):,}")

    # A: Omission table
    print("\nA. Summary-omission audit (cases where model answered wrong):")
    for cond, rep in [("summary-80", "summary-80"), ("summary-200", "summary-200")]:
        wrong_recs = [r for r in perq if r["conditions"].get(cond, {}).get("correct", 1) == 0]
        full_wrong = [r for r in wrong_recs
                      if r["conditions"].get("full", {}).get("correct", 0) == 1]
        absent = [r for r in wrong_recs if not r["gold_presence"][rep]["judge"]]
        present_but_wrong = [r for r in wrong_recs if r["gold_presence"][rep]["judge"]]
        print(f"\n   {cond}: wrong={len(wrong_recs)}  "
              f"(full-correct-but-{cond}-wrong: {len(full_wrong)})")
        print(f"     gold ABSENT from {cond}:       {len(absent):3d} / {len(wrong_recs)} "
              f"= {len(absent)/len(wrong_recs):.0%}  ← compression-omission failures")
        print(f"     gold PRESENT but model wrong:  {len(present_but_wrong):3d} / {len(wrong_recs)} "
              f"= {len(present_but_wrong)/len(wrong_recs):.0%}  ← model reasoning failures")

    # B: Accuracy gaps by distance bin
    print("\nB. Full-vs-summary accuracy gaps by evidence distance (turns):")
    hdr = f"   {'bin':<10} {'n':>4}  {'full':>6}  {'s80':>6}  {'s200':>6}  "
    hdr += f"{'w10':>6}  {'blind':>6}  {'f-s80':>6}  {'f-s200':>6}  {'f-w10':>6}"
    print(hdr)
    print("   " + "-" * 75)
    for b in ["near", "mid", "far", "ALL"]:
        if b == "ALL":
            recs = perq
        else:
            recs = [r for r in perq if r["evidence_distance_turns"].get("distance_bin") == b]
        if not recs:
            continue
        full_a,  _ = acc(recs, "full")
        s80_a,   _ = acc(recs, "summary-80")
        s200_a,  _ = acc(recs, "summary-200")
        w10_a,   _ = acc(recs, "window-10")
        blind_a, _ = acc(recs, "blind")
        n = len(recs)
        print(f"   {b:<10} {n:>4}  {full_a:6.2f}  {s80_a:6.2f}  {s200_a:6.2f}  "
              f"{w10_a:6.2f}  {blind_a:6.2f}  "
              f"{full_a-s80_a:+6.2f}  {full_a-s200_a:+6.2f}  {full_a-w10_a:+6.2f}")

    # Dispersion guard for full−summary-80 gap
    print("\n   Dispersion guard (full−summary-80, per question):")
    gap_vals = []
    for r in perq:
        fc = r["conditions"].get("full", {}).get("correct", 0)
        sc = r["conditions"].get("summary-80", {}).get("correct", 0)
        gap_vals.append((r["q_uid"], fc - sc))
    pos_gaps = [(uid, g) for uid, g in gap_vals if g > 0]
    neg_gaps = [(uid, g) for uid, g in gap_vals if g < 0]
    zero_gaps = [(uid, g) for uid, g in gap_vals if g == 0]
    print(f"   full>sum80: {len(pos_gaps)}  full==sum80: {len(zero_gaps)}  full<sum80: {len(neg_gaps)}")
    total_gap = sum(g for _, g in pos_gaps) or 1
    if pos_gaps:
        top5 = sorted(pos_gaps, key=lambda x: -x[1])[:5]
        top1_share = top5[0][1] / total_gap
        top3_share = sum(g for _, g in top5[:3]) / total_gap
        print(f"   Top-1 carries {top1_share:.0%} of total gap; top-3 carries {top3_share:.0%}")
        print(f"   {'Spread across questions' if top1_share < 0.3 else 'CONCENTRATED — check top questions'}")

    # ── Save ──────────────────────────────────────────────────────────────────
    device_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    prov = stamp(
        script="locomo_audit.py",
        model="qwen7b",
        device=device_name.lower().replace(" ", "_"),
        n=len(perq),
        args=type("A", (), {
            "scorer":                "exact_normalized_substring",
            "omission_judge":        "qwen2.5-7b_yes_no_presence",
            "evidence_distance_method": "locomo_dia_id_annotation",
            "llm_judge_calls":       judge_calls,
            "ceiling_cat1":          total_cat1,
        })(),
    )

    out = {
        "metadata": {
            "audit_n":                    len(perq),
            "ceiling_cat1":               total_cat1,
            "scorer":                     "exact_normalized_substring",
            "omission_judge":             "qwen2.5-7b_yes_no_presence",
            "evidence_distance_method":   "locomo_dia_id_annotation",
            "representations_audited":    ["full", "summary-80", "summary-200"],
            "llm_judge_calls_omission":   judge_calls,
            "timestamp":                  datetime.now().isoformat(),
        },
        "records": perq,
        "_provenance": prov,
    }
    _save_json(OUT_PATH, out)
    print(f"\nSaved → {OUT_PATH}")
    print("Do not stage or commit.")


if __name__ == "__main__":
    run_audit()
