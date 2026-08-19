"""
LoCoMo Scaled Audit — n=all-cat1 (up to 282)
==============================================
Scales the LoCoMo incompressibility result from n=50 to the full clean
single-hop (cat=1) subset. Uses pre-computed per-conversation summaries
(locomo_summaries_80/200.json) — no summarization LLM calls.

Conditions: blind, window-10, summary-80, summary-200, full
Scorer: exact normalized substring (primary) + lazy Qwen2.5-7B judge (on misses)
Omission audit: is gold present in each representation? (exact then LLM judge)
Evidence distance: via LoCoMo dia_id annotations

Sampling: all available cat=1 questions, up to --limit (default 282).
          Random seed controls order; first --limit taken.

Reports A–D:
  A. full-vs-summary-80/200/window-10 accuracy gaps with 95% Wilson CIs
     and McNemar paired significance tests.
  B. Summary-omission fractions (gold absent from summary among wrong cases).
  C. Dispersion guard: per-question gap concentration.
  D. Evidence-distance distribution.

Output: results/locomo_audit_scaled_qwen7b.json
"""

import argparse
import gc
import json
import math
import random
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from scipy import stats as scipy_stats

import torch

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "experiments" / "lib"))
from _provenance import stamp

DATA_PATH   = ROOT / "data"  / "locomo" / "locomo10.json"
SUM80_PATH  = ROOT / "results" / "locomo_summaries_80.json"
SUM200_PATH = ROOT / "results" / "locomo_summaries_200.json"
OUT_PATH    = ROOT / "results" / "locomo_audit_scaled_qwen7b.json"

MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"
DEVICE   = "cuda:0"

CONDITIONS = ["blind", "window-10", "summary-80", "summary-200", "full"]

QA_PROMPT = (
    "The following is a conversation history between two people.\n\n"
    "{context}\n\n"
    "Question: {question}\n"
    "Answer as briefly as possible (a few words). Answer:"
)
BLIND_PROMPT = (
    "Question: {question}\n"
    "Answer as briefly as possible (a few words). Answer:"
)
JUDGE_PROMPT = (
    "Is '{pred}' a correct or semantically equivalent answer to '{gold}'?\n"
    "Reply YES or NO only."
)
PRESENCE_PROMPT = (
    "Does the following text contain the answer or fact '{gold}'?\n"
    "Text: {text}\n\n"
    "Reply YES or NO only."
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize(s):
    return re.sub(r"\s+", " ", str(s).lower().strip())

def _save_json(path, obj):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    tmp.replace(path)


# ── Data loading ──────────────────────────────────────────────────────────────

def load_data(data_path, limit=0, seed=42):
    raw = json.loads(data_path.read_text())
    questions, convs = [], {}

    for item in raw:
        cid = item["sample_id"]
        c   = item["conversation"]
        sessions, dates, all_turns = [], [], []
        i = 1
        while f"session_{i}" in c:
            turns = c[f"session_{i}"]
            sessions.append(turns)
            dates.append(c.get(f"session_{i}_date_time", ""))
            all_turns.extend(turns)
            i += 1

        lines = []
        for si, (sess, date) in enumerate(zip(sessions, dates)):
            hdr = f"[Session {si+1}" + (f" — {date}]" if date else "]")
            lines.append(hdr)
            for t in sess:
                lines.append(f"{t['speaker']}: {t['text']}")
            lines.append("")
        full_text = "\n".join(lines).strip()

        convs[cid] = {
            "sessions": sessions, "dates": dates,
            "all_turns": all_turns, "full_text": full_text,
            "speaker_a": c.get("speaker_a", "A"),
            "speaker_b": c.get("speaker_b", "B"),
        }

        for qi, qa in enumerate(item["qa"]):
            if qa["category"] != 1:
                continue
            questions.append({
                "q_uid":    f"{cid}_q{qi:04d}",
                "conv_id":  cid,
                "question": qa["question"],
                "gold":     str(qa["answer"]),
                "category": qa["category"],
                "evidence": qa.get("evidence", []),
            })

    rng = random.Random(seed)
    rng.shuffle(questions)
    if limit > 0:
        questions = questions[:limit]
    return questions, convs


def build_context(cond, conv, sum80, sum200):
    sessions, dates = conv["sessions"], conv["dates"]
    if cond == "blind":
        return ""
    if cond == "window-10":
        sess = sessions[-10:]
        d    = dates[-10:]
        lines = []
        for si, (s, date) in enumerate(zip(sess, d)):
            hdr = f"[Session {si+1}" + (f" — {date}]" if date else "]")
            lines.append(hdr)
            for t in s:
                lines.append(f"{t['speaker']}: {t['text']}")
            lines.append("")
        return "\n".join(lines).strip()
    if cond == "summary-80":
        return sum80
    if cond == "summary-200":
        return sum200
    if cond == "full":
        return conv["full_text"]
    return ""


# ── Evidence distance ─────────────────────────────────────────────────────────

def ev_distance(evidence_list, all_turns):
    dia_to_idx = {t["dia_id"]: i for i, t in enumerate(all_turns)}
    idxs = [dia_to_idx[e] for e in evidence_list if e in dia_to_idx]
    if not idxs:
        return {"found": False, "turns_from_end": -1, "distance_bin": "not_found"}
    dist = len(all_turns) - 1 - max(idxs)
    bin_ = "near" if dist <= 5 else ("mid" if dist <= 20 else "far")
    return {"found": True, "turns_from_end": dist, "distance_bin": bin_,
            "method": "locomo_dia_id_annotation"}


# ── LLM ──────────────────────────────────────────────────────────────────────

def load_llm():
    from transformers import AutoTokenizer, AutoModelForCausalLM
    print(f"Loading {MODEL_ID} ...", flush=True)
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, dtype=torch.float16, device_map=DEVICE)
    model.eval()
    return model, tok


def _run(model, tok, prompt, max_new=40):
    fmt = tok.apply_chat_template([{"role": "user", "content": prompt}],
                                   tokenize=False, add_generation_prompt=True)
    inp = tok(fmt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**inp, max_new_tokens=max_new, do_sample=False,
                              pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][inp["input_ids"].shape[1]:],
                      skip_special_tokens=True).strip()


def score(pred, gold, model, tok):
    """Returns (exact, judge). Judge called lazily on exact misses."""
    p_n, g_n = _normalize(pred), _normalize(gold)
    if g_n in p_n or p_n in g_n:
        return 1, 1
    resp = _run(model, tok, JUDGE_PROMPT.format(pred=pred, gold=gold), max_new=4)
    return 0, int(resp.upper().startswith("YES"))


def check_presence(text, gold, model, tok):
    if _normalize(gold) in _normalize(text):
        return {"exact": True, "judge": True, "judge_called": False}
    resp = _run(model, tok, PRESENCE_PROMPT.format(gold=gold, text=text[:3000]), max_new=4)
    return {"exact": False, "judge": resp.upper().startswith("YES"), "judge_called": True}


# ── Statistics ────────────────────────────────────────────────────────────────

def wilson_ci(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2*n)) / denom
    margin = z * math.sqrt(p*(1-p)/n + z**2/(4*n**2)) / denom
    return p, max(0, centre - margin), min(1, centre + margin)


def mcnemar(pairs_a, pairs_b):
    """McNemar test: pairs_a[i] and pairs_b[i] are binary correct/wrong for each question."""
    b = sum(1 for a, b_ in zip(pairs_a, pairs_b) if a == 1 and b_ == 0)
    c = sum(1 for a, b_ in zip(pairs_a, pairs_b) if a == 0 and b_ == 1)
    if b + c == 0:
        return float('nan'), float('nan')
    chi2 = (abs(b - c) - 1)**2 / (b + c)
    p = 1 - scipy_stats.chi2.cdf(chi2, df=1)
    return chi2, p


# ── Main ──────────────────────────────────────────────────────────────────────

def run(limit=0, seed=42):
    questions, convs = load_data(DATA_PATH, limit=limit, seed=seed)
    sum80  = json.load(SUM80_PATH.open())
    sum200 = json.load(SUM200_PATH.open())
    total_cat1 = sum(1 for item in json.loads(DATA_PATH.read_text())
                     for q in item["qa"] if q["category"] == 1)

    print(f"Running scaled audit: n={len(questions)} / {total_cat1} cat=1 available", flush=True)

    model, tok = load_llm()

    from transformers import AutoTokenizer as AT
    tok_survey = AT.from_pretrained(MODEL_ID)
    full_tok_len = {cid: len(tok_survey.encode(cv["full_text"], add_special_tokens=False))
                    for cid, cv in convs.items()}
    del tok_survey

    records = []
    answer_judge_calls = 0
    omission_judge_calls = 0

    for i, q in enumerate(questions):
        cid  = q["conv_id"]
        cv   = convs[cid]
        gold = str(q["gold"])
        ev   = ev_distance(q["evidence"], cv["all_turns"])

        rec = {
            "q_uid":                  q["q_uid"],
            "conv_id":                cid,
            "question":               q["question"],
            "gold":                   gold,
            "evidence":               q["evidence"],
            "evidence_distance":      ev,
            "full_context_tokens":    full_tok_len[cid],
            "conditions":             {},
        }

        for cond in CONDITIONS:
            ctx  = build_context(cond, cv, sum80.get(cid, ""), sum200.get(cid, ""))
            if cond == "blind":
                prompt = BLIND_PROMPT.format(question=q["question"])
            else:
                prompt = QA_PROMPT.format(context=ctx, question=q["question"])
            pred = _run(model, tok, prompt, max_new=40).split("\n")[0].strip()
            em, jd = score(pred, gold, model, tok)
            if em == 0:
                answer_judge_calls += 1
            rec["conditions"][cond] = {"pred": pred, "exact": em, "correct": jd}

        # Omission audit: full, summary-80, summary-200
        presence = {}
        for rep, text in [("full",        cv["full_text"]),
                           ("summary-80",  sum80.get(cid, "")),
                           ("summary-200", sum200.get(cid, ""))]:
            res = check_presence(text, gold, model, tok)
            presence[rep] = res
            if res["judge_called"]:
                omission_judge_calls += 1
        rec["gold_presence"] = presence

        bin_ = ev.get("distance_bin", "?")
        s80c = rec["conditions"]["summary-80"]["correct"]
        fc   = rec["conditions"]["full"]["correct"]
        print(f"  {i+1:3d}/{len(questions)} [{bin_:8s}] "
              f"full={fc} s80={s80c} "
              f"gold-in-s80={presence['summary-80']['judge']} "
              f"gold={repr(gold[:30])}", flush=True)
        records.append(rec)

    gc.collect()
    torch.cuda.empty_cache()

    # ── Report ────────────────────────────────────────────────────────────────

    def _acc(recs, cond):
        v = [r["conditions"][cond]["correct"] for r in recs if cond in r["conditions"]]
        return v

    full_v = _acc(records, "full")
    s80_v  = _acc(records, "summary-80")
    s200_v = _acc(records, "summary-200")
    w10_v  = _acc(records, "window-10")
    bld_v  = _acc(records, "blind")
    n = len(full_v)

    print("\n" + "=" * 90)
    print("LOCOMO SCALED AUDIT RESULTS")
    print("=" * 90)

    print(f"\nD. Evidence-distance distribution (n={n}):")
    dist_bins = defaultdict(list)
    for r in records:
        dist_bins[r["evidence_distance"].get("distance_bin", "not_found")].append(r)
    for b in ["near", "mid", "far", "not_found"]:
        recs = dist_bins[b]
        if recs:
            avg = sum(r["evidence_distance"].get("turns_from_end", 0) for r in recs) / len(recs)
            tok_from_end = [r["full_context_tokens"] -
                            (r["evidence_distance"].get("turns_from_end", 0) * 50)
                            for r in recs]
            print(f"   {b:10s}: n={len(recs):3d}  avg_turns_from_end={avg:.0f}")
    all_far = all(r["evidence_distance"].get("distance_bin") == "far" for r in records)
    if all_far:
        print("   → All questions are uniformly FAR. No near/mid cases at this n.")

    print(f"\nC. Full context token lengths: "
          f"min={min(full_tok_len.values()):,}  "
          f"max={max(full_tok_len.values()):,}  "
          f"mean={sum(full_tok_len.values())//len(full_tok_len):,}")

    print(f"\nA. Accuracy (n={n})  [95% Wilson CI]")
    rows = [("blind",       bld_v),
            ("window-10",   w10_v),
            ("summary-80",  s80_v),
            ("summary-200", s200_v),
            ("full",        full_v)]
    print(f"   {'cond':<14} {'acc':>6}  {'CI':>20}  {'f-cond':>8}")
    print("   " + "-" * 55)
    full_p = sum(full_v)/n
    for label, v in rows:
        p, lo, hi = wilson_ci(sum(v), len(v))
        diff = full_p - p if label != "full" else 0
        print(f"   {label:<14} {p:6.3f}  [{lo:.3f}, {hi:.3f}]  {diff:+8.3f}")

    print(f"\n   Paired McNemar tests (full vs condition), n={n}:")
    for label, v in [("window-10", w10_v), ("summary-80", s80_v), ("summary-200", s200_v)]:
        chi2, p = mcnemar(full_v, v)
        sig = "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "n.s."))
        print(f"   full vs {label:<14}: chi2={chi2:.2f}  p={p:.4f}  {sig}")

    print(f"\nB. Summary-omission audit:")
    for cond, rep in [("summary-80", "summary-80"), ("summary-200", "summary-200")]:
        wrong = [r for r in records if r["conditions"][cond]["correct"] == 0]
        full_right_cond_wrong = [r for r in wrong
                                  if r["conditions"]["full"]["correct"] == 1]
        absent  = [r for r in wrong if not r["gold_presence"][rep]["judge"]]
        present = [r for r in wrong if     r["gold_presence"][rep]["judge"]]
        nw = len(wrong)
        print(f"\n   {cond}: n_wrong={nw}  "
              f"(full_correct_but_{cond}_wrong={len(full_right_cond_wrong)})")
        p_abs, lo_abs, hi_abs = wilson_ci(len(absent), nw)
        print(f"     gold ABSENT  (compression-omission): "
              f"{len(absent):3d}/{nw} = {p_abs:.0%}  CI=[{lo_abs:.0%}, {hi_abs:.0%}]")
        print(f"     gold PRESENT (model reasoning fail): "
              f"{len(present):3d}/{nw} = {1-p_abs:.0%}")

    print(f"\n   Omission by distance (summary-80 wrong cases):")
    s80_wrong = [r for r in records if r["conditions"]["summary-80"]["correct"] == 0]
    for b in ["near", "mid", "far"]:
        recs = [r for r in s80_wrong
                if r["evidence_distance"].get("distance_bin") == b]
        if recs:
            absent = sum(1 for r in recs if not r["gold_presence"]["summary-80"]["judge"])
            print(f"     {b}: {absent}/{len(recs)} = {absent/len(recs):.0%} absent")

    print(f"\nC. Dispersion guard (full − summary-80 per question):")
    gaps = [(r["q_uid"], r["conditions"]["full"]["correct"] -
                          r["conditions"]["summary-80"]["correct"]) for r in records]
    pos  = [(u, g) for u, g in gaps if g > 0]
    zero = [(u, g) for u, g in gaps if g == 0]
    neg  = [(u, g) for u, g in gaps if g < 0]
    print(f"   full>s80: {len(pos)}  equal: {len(zero)}  full<s80: {len(neg)}")
    total_gap = sum(g for _, g in pos) or 1
    if pos:
        top5 = sorted(pos, key=lambda x: -x[1])[:5]
        t1 = top5[0][1] / total_gap
        t3 = sum(g for _, g in top5[:3]) / total_gap
        print(f"   Top-1 carries {t1:.0%} of gap; top-3 carries {t3:.0%}")
        print(f"   {'SPREAD' if t1 < 0.3 else 'CONCENTRATED'} across questions")

    # ── Save ──────────────────────────────────────────────────────────────────
    device_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    prov = stamp(
        script="locomo_audit_scaled.py",
        model="qwen7b",
        device=device_name.lower().replace(" ", "_"),
        n=n,
        args=argparse.Namespace(
            scorer="exact_normalized_substring_plus_lazy_llm_judge",
            omission_judge="qwen2.5-7b_yes_no_presence",
            evidence_distance_method="locomo_dia_id_annotation",
            sampling=f"random_seed{seed}_from_{total_cat1}_cat1",
            answer_judge_calls=answer_judge_calls,
            omission_judge_calls=omission_judge_calls,
            ceiling_cat1=total_cat1,
            conditions=CONDITIONS,
            summaries_source="pre_cached_locomo_summaries_80_200_json",
        ),
    )
    out = {
        "metadata": {
            "n": n, "ceiling_cat1": total_cat1,
            "sampling": f"random seed={seed}, first {limit or total_cat1} from {total_cat1} cat=1",
            "conditions": CONDITIONS,
            "scorer": "exact_normalized_substring_plus_lazy_llm_judge",
            "omission_judge": "qwen2.5-7b_yes_no_presence",
            "evidence_distance_method": "locomo_dia_id_annotation",
            "summaries_source": "pre_cached_locomo_summaries_80_200_json",
            "answer_judge_calls": answer_judge_calls,
            "omission_judge_calls": omission_judge_calls,
            "timestamp": datetime.now().isoformat(),
        },
        "records": records,
        "_provenance": prov,
    }
    _save_json(OUT_PATH, out)
    print(f"\nSaved → {OUT_PATH}")
    print("Do not stage or commit.")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="Max questions (0 = all cat=1, up to 282)")
    ap.add_argument("--seed",  type=int, default=42)
    args = ap.parse_args()
    run(limit=args.limit, seed=args.seed)


if __name__ == "__main__":
    main()
