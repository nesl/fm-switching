<!-- StudyB-baselines (D134 addendum). FAITHFUL = unchanged from the original; ADAPTATION = changed, with its reason. Fairness rules 1-6 of the addendum hold for this baseline and are checked by `interface.check_fairness` and the smoke harness. -->
# Cascade routing — Dekoninck, Baader, Vechev — case D, D134 item 7

**Paper.** J. Dekoninck, M. Baader, M. Vechev, "A Unified Approach to Routing and Cascading for
LLMs", **ICML 2025**, PMLR 267:12987-13010 (arXiv:2410.10347, v1 14 Oct 2024, last revised
22 May 2025). **Code.** `https://github.com/eth-sri/cascade-routing`, cited in the paper's own
footnote. **Located, not cloned**; this card and the adapted policy are written from the paper.
Licence not yet checked, flagged for the user as with Ekya and SimpleStream.

**Files.** `cascade_routing_adapted.py`. **Experiment:** C-mixed.

## IT IS NOT A DUPLICATE OF `confidence-cascade`, AND THAT WAS CHECKED FIRST

D134 item 7 asked whether `confidence-cascade` already implements this method. It does not, and the
distinction is the paper's entire contribution.

| arm | what it does | can it skip the small model? | can it escalate after seeing an answer? |
|---|---|---|---|
| `confidence-cascade` (FrugalGPT + AutoMix) | fixed cascade ORDER, stop at the first answer a scorer trusts | **no** | yes |
| `routellm`, `hybrid-llm` | one-shot ROUTE to a single model | yes | **no** |
| **`cascade-routing` (this card)** | re-decides at each step over ordered model sets | **yes** | **yes** |

Routing chooses one model per query; cascading runs increasingly larger models until an answer is
good enough. The paper proves these are both special cases of one strategy and that the unified
rule is optimal under its formulation.

## The paper's algorithm

At step *j*, with the first *j-1* models already run, consider every **supermodel** (an ordered set
of models) containing those already run. Pick the supermodel maximising **expected quality minus
lambda times expected cost**, with lambda set so an expected cost budget B is met. If the chosen
supermodel adds no unrun model, **stop** and return the answer in hand; otherwise **run the
cheapest unrun model in it**. Supermodel quality is the expected quality of its best member, its
cost the sum of its members'. Quality estimates are **ex-ante** from small trained classifiers and
**post-hoc** updated after each model's output, so a low-confidence first answer can lower the
estimated quality and raise the estimated cost of continuing. Supermodels containing a model with
negative marginal gain are pruned. Reported gains: 1-4 % AUC over baselines on RouterBench, up to
14 % on SWE-Bench.

## Mapping, step by step

Our model set is two: **device 4B-I** and **cloud 32B**, cost-ordered. The supermodels are
`{device}`, `{cloud}` and `{device, cloud}`.

| paper | our code | note |
|---|---|---|
| supermodels over the model set | `{device}`, `{cloud}`, `{device, cloud}` | FAITHFUL, with the set we have |
| run the cheapest unrun model in the chosen supermodel | `RecallAction(decision="DEVICE")`, then `"CLOUD"` on a later epoch | FAITHFUL in mechanism |
| chosen supermodel adds nothing unrun, so stop | keep the device answer, emit no cloud recall | FAITHFUL |
| **post-hoc quality update after the first model** | `q.device_answer_confidence`, the StudyD13 logprob | **FAITHFUL in channel.** This is a LIVE channel, checked before the arm was written: `reads_device_answer` is declared at `interface.py:370`, read at `coordinator.py:171` into `self.reads_device`, and passed into `cstate.observation(...)`; the field is supplied only to arms that declare it. |
| ex-ante quality from trained classifiers | the committed ordinal `REP_QUALITY`-style priors plus readiness | **ADAPTATION.** Training a quality classifier needs a GPU and a labelled split we do not hold for this purpose. We keep the paper's DECISION RULE and substitute committed priors for its learned estimator. **Consequence: this tests the paper's selection rule, not its estimator** - and the paper's own conclusion is that estimator quality is the critical factor, so this limitation is material and is restated below. |
| cost estimates from tokens and latency | `costs.recall_gpu_s` and `costs.recall_ttft_s` on the committed curves | FAITHFUL |
| lambda set so the budget is met | derived from `obs.budget_remaining_gpu_s` against the window | **ADAPTATION**, the natural reading of "lambda set so budget B is met" with a live budget |
| variance of each estimate, measured on a validation set | **not ported** | we have no validation split for it; the rule degenerates to the expectation, which the paper's own formulation allows |

## Limitations, stated

- **This tests the selection rule, not the estimator.** The paper says good quality estimators are
  the critical factor; ours are committed ordinal priors, not trained classifiers. A weak result
  here is evidence about the rule under our estimators and **not** evidence against the paper.
- **Two models, not a ladder.** With `|M| = 2` the supermodel set has three members, so the
  pruning and search machinery is exercised only trivially. The mechanism under test is the
  skip-or-cascade choice, which two models do express.
- **Estimate variance is not ported**, so the gamma tie-breaking between cheapest and most
  expensive tied options is unused.

## D134 item 7, added 2026-11-19: it can NAME RICH but cannot RECEIVE it

Measured at 8 devices, seed 4: the arm emits `CLOUD/RICH` on one query and `CLOUD/RECENT` on eight,
and **enacts exactly that**.

**But RICH is not a representation live2 can deliver.** `cstate` builds only two evidence items,
`EvidenceItem("RECENT", ...)` and `EvidenceItem("D2", ...)` (`cstate.py:481-483`), and
`tokens_for_representation` branches on the single literal `"RECENT"` and returns the whole history
for everything else (`cstate.py:130-132`). So this arm's RICH request is **charged as full history
and served D2 content**. Session 2's accuracy join normalises anything not literally RECENT to D2
and **refuses rather than keying to K1**, since no per-question D2 cell exists.

**Its mixed representation is its MECHANISM, not a confound.** Cascade routing selects evidence by
a quality-against-cost tradeoff; an arm that emits one representation for one query and another for
the next is doing the thing the paper describes. This is the only arm in the field for which a
mixed representation is the result rather than an artefact of injected defaults.

**Therefore a single effective-representation label for this arm is wrong by construction**, and it
cannot be placed on either side of the cross-group line. It may not be compared cleanly against a
pure-side arm: part of any difference would be its scheduling and part the evidence discount, and
nothing in the comparison separates them.

**One consequence for reading its results.** Because RICH collapses to D2 in both cost and content,
the arm's three-way choice is effectively two-way on this tree. Its selection rule is intact; its
option set is smaller than the card's mapping table implies, and that narrowing is the harness's,
not the paper's.

### RICH is not a separate case, established from three independent directions

The note above records that this arm can **name** RICH but cannot **receive** it. That now rests on
three routes that agree, which is a stronger warrant than any one of them:

1. **Static.** `cstate` builds exactly two evidence items, `RECENT` and `D2`
   (`cstate.py:481-483`), and `tokens_for_representation` branches on the single literal
   `"RECENT"` (`cstate.py:130-132`).
2. **Runtime.** A census across twelve arms found **zero** RICH emissions.
3. **The live request format.** StudyACC2's design note states that **RICH = D2 in the live request
   format** — the live body carries exactly the D2 history — **so only one of them is run.**

**Consequence: RICH is dropped from the analysis rather than carried as a third representation.**
For this arm specifically that means its three-way choice is **two-way on this tree**, and that is
a fact about the evidence the harness can deliver rather than about the method. The selection rule
is intact; the option set is smaller than this card's mapping table implies.

This also disposes of the one place the D137 item 3 quality substitution could have changed a
decision: the ordinal table ties D2 and RICH at 1.0 while the measured table separates them, and
that tie is unreachable precisely because RICH is never offered.

### 2026-11-19: lambda was STRUCTURALLY PINNED, and the positive control caught it before the run

`_lmbda` read `getattr(obs, "budget_total_gpu_s", 0.0)`. **That field does not exist** —
`Observation` carries `budget_remaining_gpu_s` only. The `getattr` returned its default of `0.0`
silently, the `total > 1e-9` guard failed, `frac_spent` was pinned at `0.0`, and **lambda collapsed
to a constant `lambda_base = 0.0200` forever.** The arm was configured for price response
(`LAMBDA_SQUEEZE = 8.0`) and structurally incapable of it.

**Why this mattered more than a bug.** This arm was added to the pressure run *because* it is the
only one whose objective prices representation directly — the only instrument able to distinguish
"pressure does not move representation choice" from "no arm present could respond". Pinned, it
would have passed every check and **guaranteed the null it was added to prevent**.

**The error shape, which recurred four times this week: a DECLARATION read as an OBSERVATION.**
`getattr` with a default is the most dangerous member of that family because it **manufactures the
plausible value itself** — a plain attribute access would have raised. The others:
`RecallQuery.category` carrying the literal `"recall"`, `desired_tier` written and never read, and
a sufficiency proxy that could never fire.

**The fix is option 2, confined to this file, and the paper is what decides it.** The paper
calibrates lambda **offline** so expected cost meets a budget `B`; it does **not** read `B` at
decision time, so `Observation` is not missing a field the method requires. The rising schedule
here is the **adaptation this card already declares** — the online analogue of "lambda set so `B`
is met", i.e. feedback on consumption. Adding `budget_total_gpu_s` to a schema every arm shares, in
order to serve an adaptation rather than the paper's own formulation, would be scope creep on a
shared surface.

So the cap is **derived from what the arm has observed**: at the start of a window
`budget_remaining_gpu_s` *is* the total, so the largest remaining ever seen converges to the total
on the first epoch. That is a quantity the arm legitimately knows, not a constant smuggled in.

**Stated limitation:** an arm joining mid-window under-estimates the total and so under-reacts.
Declared rather than silent.

**Verified by positive control**, the same instrument that found the fault: lambda now rises
`0.0200 -> 0.0600 -> 0.1000 -> 0.1400 -> 0.1800` as remaining falls `600 -> 450 -> 300 -> 150 -> 0`.
Legality and the fairness digest re-checked after the fix: **0 illegal actions** across 3,001
epochs at 8 devices, digest unchanged.
