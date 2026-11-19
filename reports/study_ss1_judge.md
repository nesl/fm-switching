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

*(pending — the judge run is in progress; this section is filled from
`egothink_device_judge.json` and `egothink_device_judge_agreement.json`)*
