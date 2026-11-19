# StudySS1-judge — the open LLM judge against the containment scorer

**Scope:** EgoThink, device tier. Scorer (a) is the open LLM judge; scorer (b) is containment.
This report is about **whether the two scorers agree and where they do not**, because two scorers
disagreeing is a measurement problem to find before the numbers are used, not after.

---

## Setup, and one thing the next host needs

**Judge:** `mistralai/Mistral-7B-Instruct-v0.2`, served with vLLM 0.8.5 on the **A6000**,
`--dtype bfloat16 --max-model-len 8192 --max-num-seqs 16 --seed 0`, greedy
(`temperature=0, seed=0`), `max_tokens=512`.

> ### `head_dim: null` — the override the second host will also need
>
> **Serving `Mistral-7B-Instruct-v0.2` from the local HF cache fails on vLLM 0.8.5** with
> `TypeError: unsupported operand type(s) for *: 'int' and 'NoneType'` at
> `llama.py:135`, `self.q_size = self.num_heads * self.head_dim`.
>
> **Cause:** the cached `config.json` sets `"head_dim": null` explicitly, and this vLLM version
> dereferences it rather than deriving it.
>
> **Fix:** add `--hf-overrides '{"head_dim": 128}'` to the `vllm serve` command. **128 is
> `hidden_size / num_attention_heads` = 4096 / 32**, so it is the model's own value and not a
> tuning choice. The cached model is **not** modified.
>
> **This is recorded here rather than in a session note because the H100 runs the identical judge
> on the 32B answers and will meet the same failure.** The error does not suggest its own fix, and
> the point of a shared kit is that the second host does not re-derive what the first established.

**Prompt and scorer constancy.** `experiments/casestudy/ss1_judge.py` is run **unchanged** on both
the 4B and the 32B answers. Per-dimension agreement and the disagreement analysis live in a
**separate** file, `ss1_judge_agreement.py`, precisely so the shared script stays byte-identical:
any prompt or scorer drift between the two runs would turn a **model** comparison into a **scorer**
comparison, and that difference would be invisible in the numbers.

Judge prompt hashes, recorded so drift is **detectable** rather than assumed absent:

| component | sha256 (first 16) | length |
|---|---|---|
| `EGOTHINK_JUDGE_SYSTEM` | `75357d685f238b6a` | 28 |
| `EGOTHINK_JUDGE_TEMPLATE` | `ed38861d0f82d2d0` | 1161 |

**Deviation from the paper, stated explicitly:** EgoThink's protocol uses **GPT-4** as the judge;
this uses **Mistral-7B-Instruct-v0.2**. A 7B open judge is not a drop-in for GPT-4, and the
agreement figure below is the evidence for how far from one it is. The judge is text-only and is
**not** shown the image, which is EgoThink's own stipulation.

**Run under test:** `results/casestudy/study_ss1/egothink_device.json` — 700 answers, 0 errors,
12 dimensions, greedy, `tier=device`, `model=qwen3vl4b`.

> **Provenance gap, flagged rather than assumed away.** That file carries **no `_provenance`
> block**: `git_commit`, `script`, `model`, `device` and `timestamp` are all absent. It records
> only `tier=device`. **I cannot confirm from the file whether these answers were produced on the
> Jetson Orin or on the A6000 device proxy.** The brief calls them the Orin's. CLAUDE.md requires
> the block; it is missing, and this result inherits that ambiguity until the producing host is
> confirmed.

---

## The answer-side inputs were hash-verified at source

The 32B answer pass is produced on the H100 with its data staged and verified: **all 700 EgoThink
images hash-match the manifest**, and all 4,319 VizWiz images are present with references matching
`val.json`.

Worth recording rather than assuming, because this week supplied the counter-example: the OpenEQA
study closed cleanly **only because a published md5 was verified rather than recorded** — what
arrived was a 230 KB HTML page named `.tgz`, from a `curl` that exited 0 with the correct filename.
An input that is not hash-checked can be wrong in ways that every downstream number inherits
silently.

---

## Statistics

**Wilson score intervals**, not the normal approximation, and this is a reason rather than a
preference: per-dimension *n* is **50** for ten of the twelve dimensions (100 for two), and at that
size with agreement rates near 0 or 1 the normal interval is not valid and can cross 0 or 1. A
reader meeting a per-dimension CI would otherwise assume the usual construction.

**Judge mean and containment mean are reported per dimension alongside agreement.** Agreement alone
says the two scorers differ; the two means say **which one is lenient there**, which is the
difference between a number and a diagnosis.

**Disagreements are split by direction**, because the two directions are opposite findings and a
single disagreement count conflates them:

| direction | what it means |
|---|---|
| judge says correct, containment says 0 | **a containment failure** — a correct answer whose wording differs from the reference |
| containment says 1, judge says incorrect | **a judge failure** — the answer literally contains the reference and the judge rejected it |

A sample of each is inspected by hand below, with a verdict on which scorer I judge correct and
why. An agreement rate alone does not say which scorer is right: a judge agreeing everywhere is
redundant, one disagreeing everywhere is broken, and the interesting claim lives in between.

---

## Pre-registration

Committed **before the run** (`results/casestudy/study_ss1/judge_preregistration.json`).

**Prediction: agreement will be LOWEST on the two Planning dimensions.** Containment rewards a
literal substring of a reference; Planning answers are longer and more free-form, so a correct
answer can contain none of the reference wording, which containment scores 0 and a judge should
score 1.

**The premise was measured, not assumed**, on the answers alone with no judge involved:

| dimension | median answer words |
|---|---|
| Planning_assistance | **5.5** |
| Planning_navigation | **3.0** |
| all ten others | 1.0 to 2.0 |

Planning answers are **three to five times longer**, which is the mechanism the prediction rests
on.

**Falsification, written down in advance:** if agreement comes back **highest** on Planning, one of
the two scorers is wrong and the result must not be reported until that is resolved.

---

## Results

**Coverage first, because the first run taught that lesson.** 700 answers, **682 parsed (97.4 %)**,
18 unparsed. The superseded run on the old parser is **withdrawn**: it parsed 33 of 700 and its
`judge_mean 0.1818` / `agreement 0.5758` were computed over 4.7 % of the data. See
`results/casestudy/study_ss1/judge_parser_bug.json`.

Judge mean **0.735**, containment mean **0.465**, **overall agreement 0.633**, 95 % CI
[0.597, 0.669], n = 682.

### Agreement by dimension, Wilson 95 %

| dimension | n | agreement | 95 % CI | judge mean | containment mean |
|---|---|---|---|---|---|
| **Planning_assistance** | 50 | **0.180** | [0.098, 0.308] | 0.550 | 0.060 |
| **Planning_navigation** | 49 | **0.388** | [0.264, 0.527] | 0.459 | 0.122 |
| Reasoning_counting | 46 | 0.391 | [0.264, 0.535] | 0.663 | 0.152 |
| Activity | 98 | 0.418 | [0.326, 0.517] | 0.781 | 0.327 |
| Object_affordance | 45 | 0.644 | [0.498, 0.768] | 0.778 | 0.489 |
| Forecasting | 100 | 0.660 | [0.563, 0.745] | 0.670 | 0.450 |
| Object_existence | 49 | 0.776 | [0.641, 0.870] | 0.888 | 0.735 |
| Localization_location | 48 | 0.813 | [0.681, 0.898] | 0.958 | 0.792 |
| Reasoning_situated | 50 | 0.840 | [0.715, 0.917] | 0.830 | 0.700 |
| Object_attribute | 48 | 0.875 | [0.753, 0.941] | 0.854 | 0.792 |
| Localization_spatial | 49 | 0.878 | [0.758, 0.943] | 0.796 | 0.755 |
| Reasoning_comparing | 50 | 0.920 | [0.812, 0.969] | 0.630 | 0.620 |

### The pre-registered Planning prediction

**CONFIRMED under the scorer as committed.** `Planning_assistance` has the **lowest agreement of
all twelve dimensions at 0.180**, and its CI [0.098, 0.308] excludes every dimension from
`Object_affordance` upward. `Planning_navigation` is second lowest at 0.388, **though its interval
overlaps `Reasoning_counting` heavily and the two cannot be separated**, which is stated rather
than glossed.

The predicted **mechanism** also holds, and it is visible in the means rather than inferred: on
`Planning_assistance` the judge scores **0.550** and containment **0.060**. Containment is scoring
almost everything wrong on the dimension whose answers are longest.

### But the binarisation is doing most of the work, and that was NOT pre-registered

`ss1_judge.py` counts a judge rating as correct when `rating >= 0.5`. The judge's three-valued
output is **0.0 / 0.5 / 1.0**, distributed **112 / 137 / 433** — so **137 of 682 (20.1 %) are
"partially correct" and the rule counts every one of them as correct.**

| rule for a 0.5 rating | overall agreement |
|---|---|
| counted **correct** (as committed) | **0.633** |
| counted **incorrect** | **0.805** |

**The headline figure swings 17 percentage points on a threshold nobody registered**, and the 0.5
ratings are concentrated exactly where the disagreement is: **58 % of `Planning_assistance` and
47 % of `Planning_navigation`** are rated 0.5, against 4 % of `Object_attribute`.

Under the strict rule the ranking **inverts**: `Planning_assistance` rises 0.180 to 0.760 and
`Planning_navigation` 0.388 to 0.857, and the lowest becomes `Reasoning_counting` at 0.500.

**So the pre-registered prediction is confirmed under the committed scorer and would be refuted
under an equally defensible one.** Reported as such. The deeper and threshold-independent
statement is this: **containment is binary and has no middle category, so the two scorers disagree
most precisely where the judge uses its middle one.** That is a structural mismatch between the
scorers, not a fact about Planning.

---

## The disagreements, by direction, with verdicts

245 cases where the judge says correct and containment says 0; **only 5** the other way.

### Direction A — judge correct, containment 0 (245)

Inspected sample, with my verdict on each:

| reference | answer | verdict |
|---|---|---|
| `cultivating plants` | `Planting flowers` | **containment wrong** — synonymous |
| `Peel the onion.` | `Peel onion` | **containment wrong** — differs by one article |
| `Cleaning handrail.` | `Wiping staircase railing` | **containment wrong** — synonymous |
| `Sweep it along the handrail's surface...` | `Use brush in left hand to sweep dust off handrail.` | **containment wrong** — correct paraphrase |
| `Choosing clothes.` | `Shopping` | **ambiguous** — judge lenient |
| `Two.` | `1` | **JUDGE WRONG** — the answer is simply the wrong number |

**Mostly genuine containment failures on paraphrase, as predicted. But not uniformly**, and the
counting case is the opposite failure hiding inside the same direction.

### `Reasoning_counting` is a different failure wearing the same signature

28 of 46 disagree. The dominant pattern is the reference spelled as a word and the answer as a
digit: `Three.` vs `3`, `One.` vs `1`, `Two.` vs `2`. **Containment scores all of these 0**, which
is a word-versus-digit failure and nothing to do with compression or paraphrase.

But two cases show `Two.` vs `1` and `One.` vs `2` rated **0.5** by the judge: **numerically wrong
answers given partial credit**, which the `>= 0.5` rule then counts as correct.

**So the same low-agreement signature — judge high, containment low — has opposite causes in
different dimensions.** On Planning it is containment failing; on counting it is containment
failing *and* the judge being too generous. An agreement rate cannot distinguish them, which is why
the direction split and the inspection were necessary rather than decorative.

### Direction B — containment 1, judge wrong (5): NOT a judge-failure direction

All five inspected. **Every one is a short answer that is a substring of a longer reference while
being wrong or incomplete**, so containment scored it correct:

| reference | answer | verdict |
|---|---|---|
| `it is not flat` | `flat` | **containment wrong — NEGATION FAILURE.** The answer asserts the opposite and contains the reference's own word. |
| `Stand up first, then turn left and walk...` | `turn right` | **containment wrong** — the answer gives the opposite direction |
| `There are less mats holding in my hands.` | `hands` | containment wrong — a fragment, not an answer |
| `There are more planks on the left side...` | `left` | containment wrong — a fragment |
| `The glass. Find the location of the glass...` | `glass` | judge arguably harsh; answer omits the "how" |

**So both directions are predominantly containment failures.** Containment produces false negatives
on paraphrase (245) *and* false positives on substrings of negations (5). The judge is the better
scorer in four of the five cases that superficially look like judge failures.

---

## What this says about the two scorers

1. **Containment is not a safe fallback scorer on free-form answers.** It fails in both
   directions, and its negation failure (`flat` scored correct against `it is not flat`) is a
   correctness error, not a strictness choice.
2. **The judge is the better scorer here, but it is lenient on numeric answers**, awarding 0.5 to
   wrong numbers, which the `>= 0.5` rule promotes to correct.
3. **The overall agreement figure of 0.633 should not be quoted alone.** It is 0.805 under an
   equally defensible binarisation, and in ten of twelve dimensions the two scorers are measuring
   different things rather than agreeing or disagreeing about the same thing.
4. **High agreement is not evidence the judge is good.** Ten of twelve dimensions have median
   answers of 1 to 2 words, where a correct answer usually *is* the reference token, so the two
   scorers agree almost trivially. `Reasoning_comparing` at 0.920 has judge 0.630 against
   containment 0.620: near-identical means on short answers. The informative cells are the long
   ones, which is where the pre-registration was aimed.

---

## Limitations

- **The judge is Mistral-7B-Instruct-v0.2, not GPT-4.** Stated at the top; the deviation first bit
  at the parsing layer, before any quality question arose.
- **18 of 700 (2.6 %) carry no parseable rating** and are excluded, not imputed. Sixteen state a
  rating only in prose; forcing those would risk capturing unrelated numbers.
- **The `>= 0.5` binarisation is a scorer choice with a 17-point effect** and was not
  pre-registered. Both values are reported; neither is privileged.
- **Provenance:** the device answers carry no `_provenance` block, so the producing host (Orin or
  A6000 proxy) is unconfirmed from the file.
