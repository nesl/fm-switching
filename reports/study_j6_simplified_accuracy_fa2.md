# StudyJ6 — Accuracy Cost of the Simplified Prompt

**Date:** 2026-10-03  
**Pre-registered:** `research/EXPERIMENTS.md` row StudyJ6  
**Pre-registered decision rule:** FIX if SIMPLIFIED accuracy on terminating trials is not significantly worse than ORIGINAL (McNemar/Fisher, α=0.05 on sign pairs where both terminate); TRADE if accuracy drops significantly.

---

## §1 Scorer Validation

Gemini-2.0-Flash overall_acc = **40.7%** (J2 reference: 40.7%, paper: 42.2%).  
Deviation from J2 reference: 0.0pp — **PASS** (threshold 2pp).

Scorer: open_clip ViT-B-32/laion2b_s34b_b79k, loc=soft, sym=soft-clip.

## §2 Analysis A — Termination Rate

Termination = `think_closed=True` (model output contained `</think>`).  
Check vs StudyJ5: ORIG ≈ 25.7%, SIMP ≈ 5.7%.

| arm | trials | terminated | non-term | rate |
|---|---|---|---|---|
| ORIGINAL | 70 | 64 | 6 | 8.6% |
| SIMPLIFIED | 70 | 70 | 0 | 0.0% |

## §3 Analysis B — Accuracy

**B1 — Accuracy on terminating trials** (denominator = trials that terminated and parsed):

| arm | terminating parsed | correct | acc (terminators) |
|---|---|---|---|
| ORIGINAL | 57 | 13 | 22.8% |
| SIMPLIFIED | 70 | 10 | 14.3% |

**B2 — Deployment-realistic accuracy** (denominator = all 70 trials; non-terminating = 0 score):

| arm | total | correct-among-all | deployment acc |
|---|---|---|---|
| ORIGINAL | 70 | 13 | 18.6% |
| SIMPLIFIED | 70 | 10 | 14.3% |

## §4 Analysis C — FIX or TRADE Verdict

Paired comparison on (sign, seed) pairs where **both** arms terminated and parsed.

Paired trials (both terminated and parsed): **57**

| cell | count |
|---|---|
| both correct | 10 |
| both wrong | 44 |
| ORIG correct, SIMP wrong (b) | 3 |
| ORIG wrong, SIMP correct (c) | 0 |

McNemar exact p-value (b=3, c=0): **p = 0.2500**  
Verdict: **FIX** — SIMPLIFIED does not significantly reduce accuracy (p ≥ 0.05).

---

### CLAUDE.md Rule 2 classification — INCONCLUSIVE, not a settled FIX

**Added 2026-10-16 after the auto-generated verdict.** The pre-registered rule returns FIX
mechanically, because p = 0.25 ≥ 0.05. That verdict is not supportable as a finding, for one
arithmetic reason: with c = 0, the exact binomial test **cannot reach α = 0.05 until b = 6**.

| b (ORIG correct, SIMP wrong) | c | exact p |
|---|---|---|
| 3 | 0 | 0.2500 ← observed |
| 4 | 0 | 0.1250 |
| 5 | 0 | 0.0625 |
| 6 | 0 | **0.0312** — first value that rejects |

Only 3 discordant pairs exist in 70. The test could not have fired at this n regardless of what
the data did, so "not significant" carries no information about whether SIMPLIFIED costs
accuracy. Under CLAUDE.md Rule 2 this is **Inconclusive — a design-power failure**, not a real
negative. It is the same condition already recorded for StudyJ3 ("UNDERPOWERED — 0/8 is not
evidence of effect"); recording FIX as settled here would repeat that error.

**Every point estimate moves against SIMPLIFIED**, which is worth stating plainly even though
none of it is significant:

| measure | ORIGINAL | SIMPLIFIED | delta |
|---|---|---|---|
| accuracy on terminating+parsed | 22.8% (13/57) | 14.3% (10/70) | −8.5 pp |
| deployment-realistic (all 70, non-term = 0) | 18.6% | 14.3% | −4.3 pp |
| discordant pairs | b = 3 | c = 0 | 3–0 against |

Nothing in this data suggests SIMPLIFIED improves accuracy. The honest statement is that J6 is
too small to price the cost, and the registered question — what accuracy does the simplified
prompt buy its termination gain with — remains open.

### What IS settled here: liveness

The termination result is clean and does not depend on the underpowered accuracy test:

| | ORIGINAL | SIMPLIFIED |
|---|---|---|
| terminated | 64/70 (91.4%) | **70/70 (100%)** |
| parse failures among terminators | 7 | **0** |

SIMPLIFIED terminated on every one of 70 draws and produced parseable JSON every time; ORIGINAL
failed to terminate 6 times and emitted unparseable output 7 more. That is consistent with
StudyJ5 (ORIG 25.7% → SIMP 5.7% non-termination) and is the direction StudyJ3 suggested at
insufficient power. Think-token medians are *higher* under SIMPLIFIED (4,776 vs 4,360, §5), so
the prompt change buys termination without shortening reasoning — also matching J5.

### Parser defect found and repaired before scoring

Every trial in this run initially recorded `prediction = None`, `parse_status = parse_failed`,
`score = None` — the exact StudyJ5 failure mode. Cause: generation decodes with
`skip_special_tokens=False` (required to detect `</think>` in the raw stream), so each answer
carries a trailing `<|im_end|>`; `parse_prediction` stripped code fences but not special tokens,
so every `json.loads` failed. `study_j_signs.py` avoids this by decoding the answer with
`skip_special_tokens=True`.

Unlike StudyJ5, this run stores `answer_text`, so nothing was lost. The parser now strips
`<|...|>` before parsing and the trials were re-parsed and re-scored offline from the stored
answers: **127/140 parse (6 non-terminating + 7 genuinely malformed model outputs account for
the remaining 13)**. No inference was repeated. The pre-scoring JSONL is preserved outside the
repo.

### Run conditions

140 trials, ~6 h on a6000 (cuda:1), `flash_attention_2` asserted on all three towers and
recorded per trial. The card ran at 88 °C with `sw_thermal_slowdown` active for much of the run
(SM 1725 MHz against a 2100 MHz maximum); measured effect on decode throughput was **2.6%**
(median 42.6 → 41.5 tok/s across the first and second halves, bucketed by generated length), so
latencies here are within normal variation of the StudyJ2 flash-attn baseline (42.5 vs 42.7
tok/s median). Stated as a condition, not a defect.

Per-sign cost ranged 1.3 to 42.7 minutes. The `cap_hit`/`control` label — which reflects
StudyJ2's seed-42 outcome — did not predict cost (cap-hit mean 26.8 min; the four non-trivial
controls averaged 37.8 min). `n_gt` did: the two `n_gt = 1` signs cost ~1.5 min, everything with
`n_gt ≥ 3` cost 20–45 min.

## §5 Analysis D — Think-Token Distribution Among Completers

| arm | n completers | median | IQR | min | max |
|---|---|---|---|---|---|
| ORIGINAL | 64 | 4360 | 4656 | 252 | 16140 |
| SIMPLIFIED | 70 | 4776 | 4829 | 149 | 13117 |

Note: higher median think-tokens under SIMPLIFIED is consistent with StudyJ5 (SIMP 4433 vs ORIG 3729 tok).

## §6 Summary

| metric | ORIGINAL | SIMPLIFIED |
|---|---|---|
| trials | 70 | 70 |
| termination rate | 8.6% non-term | 0.0% non-term |
| acc (terminators) | 22.8% | 14.3% |
| deployment acc | 18.6% | 14.3% |
| paired verdict | — | FIX |

