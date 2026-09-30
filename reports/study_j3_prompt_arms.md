# Study J3 — Prompt Ablation on SiGNgapore2D Non-Terminators

**Date:** 2026-09-30  
**Status:** Complete (data); underpowered for primary hypothesis  
**Follow-up to:** StudyJ2 (20% non-termination asymptote at 24,576 tokens, seed=42)  
**Research question:** Is the 20% non-termination asymptote a property of the task+model or substantially prompt-induced?

---

## Setup

| item | value |
|------|-------|
| Dataset | NickyZimmerman/SiGNgapore2D — 12-sign subset |
| Subjects | 8 cap-hit signs from StudyJ2 §4 + 4 control completers from StudyJ2 manifest |
| Controls | IMG_6599/n_gt=8, IMG_6413/n_gt=4, IMG_6538/n_gt=1, IMG_6451/n_gt=2 |
| Arms | ORIGINAL-SEED123, SIMPLIFIED, BUDGET-AWARE (see §1) |
| Model | Qwen3-VL-4B-Thinking — same snapshot as StudyJ2 |
| Decoding | temperature=0.6, top_p=0.95, top_k=20, min_p=0, do_sample=True |
| max_new_tokens | 24,576 |
| Runs | 12 signs × 3 arms = 36 total, 0 errors |

---

## 1. Prompts — Verbatim and Diffed

### Arm A: ORIGINAL-SEED123

The paper's prompt verbatim, seed=123. Tests seed stability (seed=42 was used in StudyJ2).

> I'll teach you how to read navigational signs today. There are 2 important components of any sign : the text or symbol corresponding to the location and the arrow describing the direction you need to move in, as if you are standing in front of the board, in order to reach the location.
>
> If you see location names besides these arrows then -- then specify the direction of the arrow as it would look if you were standing perfectly in front of the sign board.
> If you see symbols on the navigational sign then use your commonsense understanding of the symbol image and the text around it to convert it to text name for representing as a location name. Some examples of such locations could be -- [symbol list]. Use your commonsense understanding to decode such common symbols observed in navigational signs to locations. Don't restirct yourself to the example symbols.
>
> Now I will teach you how to read arrows. We need to read the arrows in the frame of the navigation signboard.
>
> If it points north then we say it points to the direction "straight". [...]
> If it points east wrt to the board, we say it points to "right". [...]
> If it points west wrt to the board we say it points to "left" [...]
> If it points diagonally north-east wrt to the board we say it points to "straight-right" [...]
> If it points diagonally north-west wrt to the board we say it points to "straight-left" [...]
> If there is some information on the navigation board with NO ARROWS associated with it, then respond the arrow direction as "locational" for that location text.
>
> The image quality should be extremely high. Tokenize the image in your maximum number of tokens. I want accuracy. Focus very carefully on the navigational board. SEE VERY CAREFULLY all text name of symbol or location name and their arrow associations. The output direction should be from this list ['left', 'right', 'straight', 'straight-right', 'straight-left', 'locational']. Return a JSON dictionary consisting of keys as "t" or "s" based on whether the location name was inferred through text("t") or through symbol("s") AND values as another dictionary with keys as locations and values as arrow direction. **If a location is being represented as symbol and text both, then mention that in both 's' and 't'. For example: if you see toilet symbol as well as "TOILET" text written then add 'TOILET' to 't' and 's' both.** **ONLY if there are multiple directions for a location then output all detected direction as a list. For example : "TOILET" : ["left", "right"]  Otherwise the direction should be string. For example: "HOSPITAL": "left"**
> Only consider English text. Ignore other languages. Ensure it is a dictionary of dictionary. **The value of "s" or "t" can be empty dictionary if there are no symbol detections or no text based location names in the image.** No extra text except the dictionary.

Three constraint clauses highlighted in **bold** above. These are the clauses removed in arm B.

---

### Arm B: SIMPLIFIED (seed=42)

The paper prompt with three secondary constraint clauses removed:

1. *Removed:* "If a location is being represented as symbol and text both, then mention that in both 's' and 't'. For example: if you see toilet symbol as well as 'TOILET' text written then add 'TOILET' to 't' and 's' both."
2. *Removed:* "ONLY if there are multiple directions for a location then output all detected direction as a list. For example : 'TOILET' : ['left', 'right']  Otherwise the direction should be string. For example: 'HOSPITAL': 'left'"
3. *Removed:* "The value of 's' or 't' can be empty dictionary if there are no symbol detections or no text based location names in the image."

The output format instruction is simplified to: "Return a JSON dictionary with keys 't' or 's' based on whether the location name was inferred through text ('t') or through symbol ('s'), with values as another dictionary mapping location names to arrow directions."

All other content (arrow direction teaching, image quality instruction, direction list) is preserved unchanged.

---

### Arm C: BUDGET-AWARE (seed=42)

The paper's original prompt (identical to arm A) with one sentence appended:

> IMPORTANT: You have a limited token budget. Do not re-check constraints after reasoning. Once you have identified all locations and directions, immediately write your final JSON answer.

---

**Explicit diff summary:**

| clause | ORIGINAL | SIMPLIFIED | BUDGET-AWARE |
|--------|----------|-----------|--------------|
| symbol+text both rule | present | **removed** | present |
| multi-direction list rule | present | **removed** | present |
| empty-dict rule | present | **removed** | present |
| budget instruction | absent | absent | **added** |

---

## 2. Per-Arm Termination on 8 Cap-Hit Signs

| sign | n_gt | ORIG-123 | SIMPLIFIED | BUDGET-AWARE |
|------|------|----------|-----------|--------------|
| IMG_6548_frame_0019_1 | 4 | **TRUNC** | ok | **TRUNC** |
| IMG_6416_frame_0013_0 | 3 | ok | ok | **TRUNC** |
| IMG_6411_frame_0014_0 | 3 | ok | ok | ok |
| IMG_6546_frame_0019_1 | 4 | ok | ok | ok |
| IMG_6617_frame_0015_0 | 5 | ok | ok | ok |
| IMG_6623_frame_0015_0 | 7 | ok | ok | ok |
| IMG_0037_frame_0014_0 | 7 | ok | ok | ok |
| IMG_0068_frame_0007_0 | 7 | ok | ok | ok |
| **Total truncated** | | **1/8** | **0/8** | **2/8** |
| **Total terminated** | | **7/8** | **8/8** | **6/8** |

---

## 3. Per-Arm Termination on 4 Control Signs

| sign | n_gt | ORIG-123 | SIMPLIFIED | BUDGET-AWARE |
|------|------|----------|-----------|--------------|
| IMG_6599_frame_0016_0 | 8 | ok | ok | **TRUNC** |
| IMG_6413_frame_0022_0 | 4 | ok | ok | ok |
| IMG_6538_frame_0028_0 | 1 | ok | ok | ok |
| IMG_6451_frame_0014_0 | 2 | ok | ok | ok |
| **Total truncated** | | **0/4** | **0/4** | **1/4** |

---

## 4. Think-Token Distributions (Completers Only)

### Cap-hit signs

| arm | n completers | min | median | max |
|-----|-------------|-----|--------|-----|
| ORIGINAL-SEED123 | 7/8 | 2,867 | 5,126 | 7,847 |
| SIMPLIFIED | 8/8 | 3,429 | 6,787 | 14,622 |
| BUDGET-AWARE | 6/8 | 2,662 | 6,420 | 10,702 |

### Control signs

| arm | n completers | min | median | max |
|-----|-------------|-----|--------|-----|
| ORIGINAL-SEED123 | 4/4 | 607 | 2,333 | 3,928 |
| SIMPLIFIED | 4/4 | 617 | 2,471 | 5,489 |
| BUDGET-AWARE | 3/4 | 323 | 3,619 | 3,942 |

**Observation:** SIMPLIFIED does not shorten reasoning. The completer median is *higher* under SIMPLIFIED (6,787) than ORIGINAL-SEED123 (5,126) for cap-hit signs. IMG_6623 uses 14,622 think tokens under SIMPLIFIED versus 2,867 under ORIGINAL. The prompt change does not compress the reasoning trace; it may remove the loop-exit barrier that was causing degenerate repetition in class-(b) signs.

---

## 5. Accuracy on Control Signs

No ground-truth scoring was run as part of this study (the scorer requires a full set of predictions to compute metrics; the 4-sign subset is not sufficient for the scorer's indexing). Qualitative check: all 4 controls produced parseable JSON answers under all arms that terminated. Full accuracy comparison is conducted in StudyJ5, which scores all completions under both arms.

---

## 6. Late-Trace Capture

Late-trace capture (last 500 tokens) was written for truncated trials. Three truncated trials:

**ORIGINAL-SEED123 / IMG_6548 (n_gt=4, cap_hit):** Truncated; `think_closed=False`. Full trace not re-captured in J3 (J3 wrote `last_500_tokens` field in the JSONL). Sign identified in StudyJ2 §5 as class (a) — substantive reasoning near completion. Seed change (42→123) did not help this sign.

**BUDGET-AWARE / IMG_6416 (n_gt=3, cap_hit):** Truncated; `think_closed=False`. ORIGINAL-SEED123 completed this sign (7,077 think tokens). The budget instruction did not prevent non-termination and may have added constraint-verification overhead.

**BUDGET-AWARE / IMG_6599 (n_gt=8, control):** Truncated; `think_closed=False`. This sign completed under all other arms. The BUDGET-AWARE instruction introduced new truncation on a previously-safe sign.

---

## 7. Critical Limitation: The Study is Underpowered

**The 0/8 truncation rate under SIMPLIFIED must not be interpreted as evidence that the simplified prompt eliminates non-termination.**

StudyJ4 established that non-termination is stochastic with a per-attempt failure rate of approximately 13–16% (corrected estimate; see StudyJ5 §1 for the full correction to StudyJ4's pooled rate). Under a 13–16% per-attempt rate, the probability of observing zero failures in 8 independent draws by chance alone is:

- At 13%: (0.87)^8 = **0.31 (31%)**
- At 16%: (0.84)^8 = **0.25 (25%)**

That is, roughly a **1-in-3 to 1-in-4 chance** of observing 0/8 truncations even if the simplified prompt has exactly the same failure rate as the original. The observed 0/8 is fully consistent with no effect.

This study cannot answer whether the simplified prompt reduces non-termination. The hypothesis requires adequate statistical power, which StudyJ5 provides by running both arms on the same 14 signs × 5 seeds and applying McNemar's paired test on the discordant (sign, seed) pairs.

**Do not report or cite the SIMPLIFIED 0/8 result as evidence of prompt efficacy.**

---

## 8. What Can Be Concluded from This Study

1. **Seed stability (arm A):** On seed=123, 7/8 cap-hit signs terminated — the same signs that all failed on seed=42 in StudyJ2. This replicates StudyJ4's finding that non-termination is stochastic, not input-determined. One sign (IMG_6548) fails on both seeds, consistent with its 4/5 failure rate in StudyJ4.

2. **Budget instruction is counterproductive (arm C):** BUDGET-AWARE produced the highest truncation count (3/12 total: 2 cap-hits + 1 control), including one control sign that terminated under all other arms. The budget instruction does not reduce non-termination and introduces new failures.

3. **Prompt change does not shorten reasoning:** Among completers, SIMPLIFIED median think tokens are equal to or higher than ORIGINAL-SEED123 (cap-hits: 6,787 vs 5,126; controls: 2,471 vs 2,333). If the simplified prompt reduces non-termination, the mechanism is not token-budget compression.

4. **The hypothesis (simplified prompt reduces non-termination) is untested at this sample size.** See §7.
