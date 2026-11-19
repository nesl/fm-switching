<!-- StudyB-baselines (addendum). FAITHFUL = unchanged from the original; ADAPTATION = changed, with its reason. Fairness rules 1-6 of the addendum hold for this baseline and are checked by `interface.check_fairness` and the smoke harness. -->
# ECO-LLM (arXiv:2507.09003) — case D, P0

**Paper.** P. Patidar, A. Crown, K. Hsieh, Y. Xu, "ECO-LLM: Orchestration for Domain-specific
Edge-Cloud Language Models", arXiv:2507.09003 (11 Jul 2025, Microsoft Research). **Verified by
the arXiv API.**

> **NAME CHECK.** The id resolves to a paper whose *title* is "Orchestration for Domain-specific
> Edge-Cloud Language Models"; ECO-LLM is the system name inside it. A **different** 2024 paper,
> "ECO-LLM: LLM-based Edge Cloud Optimization", also uses the name — OpenAlex returns that one for
> a title search. The id given in the addendum is the Microsoft Research one, which is what is
> implemented here.

**Code.** None found (searched the arXiv page, the authors' pages, Microsoft Research, GitHub by
title and author; the only GitHub links in the PDF are unrelated dependencies). **Case D.**

**Files.** `reconstructed/ecollm.py`, `reconstructed/test_ecollm_toy.py`, `ecollm_adapted.py`.
**Experiments:** A-episodic, B-recall, C-mixed.

## The paper's algorithm

Its stated insight: prior work "primarily focus[es] on selecting the best LLM model ... while
neglecting the critical interplay between the components of the LLM serving pipeline", naming
RouteLLM and AutoMix as examples. ECO-LLM therefore (a) "systematically expl[ores] component
configurations" offline, with an **Emulator** that "efficiently explores the vast configuration
space", and (b) "dynamically select[s] optimal resource[s]" per query so that user-defined
**SLOs** are met while accuracy stays stable.

## Mapping, step by step

| paper | our code | note |
|---|---|---|
| configuration space | the joint product of our actions: episodic (mode, cadence, N) and recall (tier, representation) | ADAPTATION A1 |
| Emulator | `explore(space, evaluate)` with `evaluate` reading committed measurements | ADAPTATION A2 |
| SLOs | `SLO(max_latency_s, max_cost_gpu_s, min_quality)` = the query's deadline and the remaining budget | FAITHFUL in role |
| dynamic selection | `select(points, slo)`: highest quality among feasible; least-violating otherwise | FAITHFUL |
| tie-breaking | lower cost wins, matching "meets SLOs while maintaining stable accuracy" at lower cost | FAITHFUL |

## Adaptations, with reasons

- **A1 the configuration space is ours.** The paper's components include context retrieval/RAG;
  we have no retrieval stage, so the joint space is (tier, representation) for recall and
  (mode, cadence, N) for episodic. The *jointness* — the paper's whole point — is preserved.
- **A2 the Emulator is replaced by measurement.** The Emulator runs the pipeline, which needs
  inference. We read StudyE9b / E9c (episodic quality), StudyRH5 / E10b (recall service time) and
  `costs` (GPU-seconds, latency). **Consequence: our exploration is exact and exhaustive rather
  than emulated, which makes selection easier than in the paper.**
- **A3 recall representation quality is ORDINAL, not measured.** `REP_QUALITY` gives RECENT 0.6
  and D2 = RICH 1.0, from StudyRH4's committed finding that D2 = K1. These are **ordinal weights,
  not accuracies**, and no accuracy claim may be read off them. FLAGGED as the weakest input.

## Not reproduced, and why

The Emulator; the retrieval/RAG component of the configuration space; the domain-specific tuning
of its evaluation; its hardware-platform comparison.

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| SLO budget | the remaining GPU-seconds divided across live streams | our budget, not the paper's |
| recall SLO | the query's own deadline | the observation |
| `REP_QUALITY` | 0.6 / 1.0 / 1.0 | ordinal, from StudyRH4 (A3) |

## D135 item 1, added 2026-11-19: the planner now prices RECENT at what it is charged

**The defect.** eco-llm read `q.evidence` for **availability** (`have`) but ignored the `tokens`
field on the very items it was handed, pricing every representation at
`readiness_tokens * REP_TOKEN_SCALE[rep]` instead. The committed RECENT `EvidenceItem` carries
`RECENT_WINDOW_TOKENS = 467` in all three harnesses (`live/adapter.py:65`, `sim/run.py:81`,
`live2/cstate.py:50`), and since Part A live2 **charges** `min(467, history)` through
`cstate.tokens_for_representation`.

So the planner priced the cheap option at `0.35 x history` while paying `467`. The two agree only
near a history of **1,334 tokens**; measured histories in the verification run were min 1,381,
median 10,831, max 25,681, so **essentially every query sat above the crossover** and RECENT was
over-priced in eco-llm's own view by up to about 9x. It therefore under-selected RECENT exactly
where RECENT is cheapest.

**The fix.** `_rep_tokens(q, rep, ev_tok)` takes the token count from the evidence the harness
offered, falling back to the old scale when no sized item is supplied, so any harness that offers
no evidence behaves exactly as before.

**Step 2b, the move proof.** Same trace, same seed, same size, only the planner's price changed:
**3 decisions differ**, first at index 7,825, and cloud-RECENT selections rise **3 to 6**. The
direction was stated before the measurement and matched: priced correctly, eco-llm selects RECENT
about twice as often.

**Class of fault.** An arm's internal estimate diverging from the quantity actually charged. The
same class as the S2 admission-estimate fault recorded under the builder work, where the estimate
was `LlfArm`'s `S_hat` rather than B7's and the byte-identity proof passed only by regime
coincidence. There the divergence was masked; here it was live in the comparator.

**Consequence for prior numbers.** eco-llm is the comparator for the published-arm field. Rows
produced before this fix were planned under different prices and are to be relabelled
**pre-reconciliation**; re-scoring and the capacity-cell movement belong to session 2.

> **MEASUREMENT SCOPE, amended 2026-11-19.** A suspected regression in recall costing (`e924005`)
> was under isolation when this was written, so everything here was held. The fault is now located
> and is **orthogonal to this fix**: it is in the `readiness` argument of
> `cost = C.recall_gpu_s(tokens, readiness)`, while this reconciliation is entirely on the
> `tokens` side and never touches readiness. So the **selection** results above stand as reported:
> 3 decisions differ and cloud-RECENT selections rise 3 to 6.
>
> What remains held is anything expressed in **GPU-seconds** or in **served-recall counts**, since
> both flow through the broken readiness argument. No such number is quoted on this card.
>
> *Noted because it is the same failure mode as the one that produced this amendment:* my original
> note said "MEASUREMENT HELD", which was true of what I had measured and implied more scope than
> the hold actually needed. A correct sentence that implies more than it covers is harder to catch
> than a wrong one, and a card is exactly where that happens.

## D137 item 3, added 2026-11-19: measured quality substituted, and why it cannot move the selection

**The change.** `REP_QUALITY` (ordinal: RECENT 0.6, D2 1.0, RICH 1.0) is replaced by the committed
**trace-weighted** measured table, `REP_QUALITY_MEASURED` (RECENT 0.3963, D2 0.4286, RICH 0.4255).
Trace-weighted rather than per-category per D137 item 2, and because per-category cells at
n = 16 to 39 have twice been shown harmful to act on. A single switch,
`_use_measured_quality = False`, disables the change itself rather than reconstructing the prior
condition.

**The ruling's premise is right about provenance.** The card declares `REP_QUALITY` **ORDINAL and
not measured** under adaptation A3, while the paper profiles configurations offline and selects on
those profiles. Hard-coded ordinal constants are therefore a departure, and replacing them is a
correction to faithfulness on its own terms.

**But it cannot produce the effect the ruling hopes for, and the reason is structural rather than a
matter of calibration.**

1. `ecollm.select` is `max(feas, key=lambda c: (c.quality, -c.cost_gpu_s))` — a **tuple**
   comparison, so cost is consulted **only when quality is exactly equal**.
2. Quality never enters feasibility: `SLO.min_quality` is left `None` here, and `SLO.violation`
   adds a quality term only when it is set.
3. Therefore the selection depends on the **order** of the quality values and on nothing else.
   **Any two tables sharing that order produce identical decisions**, whatever the magnitudes.

The gap shrinking twelvefold, 0.4 to about 0.032, is a change in magnitude only. Against cost
differences of 11.6x to 55x it still loses, because the comparison never reaches cost.

**The one order change is unreachable.** The ordinal table **ties** D2 and RICH at 1.0 while the
measured table separates them (0.4286 against 0.4255). That tie is the only place the substitution
could alter an outcome — and `cstate` builds only `RECENT` and `D2` evidence items
(`cstate.py:481-483`), so `have` never contains RICH and the tie never arises.

**What the paper says, checked rather than assumed.** ECO-LLM "dynamically select[s] optimal
resource[s]" per query so that "user-defined SLOs are met while accuracy stays stable". That is
**SLO-constrained accuracy maximisation**: cost is a **constraint**, not a term traded against
quality. So the lexicographic rule this card already labels FAITHFUL is a fair reading, and a joint
quality-minus-cost score — which is what would let price compete directly — would itself be a
**departure** from the paper.

**Consequence, stated plainly: price can only reach this arm's decisions through FEASIBILITY.**
That is exactly how the D135 token reconciliation moved decisions at 16 devices and not at 8: it
changed cost, cost changed the budget constraint, and the constraint changed which options were
feasible. The two rulings therefore differ in kind. **D135 touched a constraint and was effective;
D137 item 3 touches a quantity used only as an ordering and cannot be.** Both are correct as
faithfulness fixes; only one can change a decision.

## D138 ruling: the lexicographic rule STAYS, and the limitation is recorded here

The user has accepted the reading of the paper recorded above — ECO-LLM selects per query so that
user-defined SLOs are met while accuracy stays stable, which is **SLO-constrained accuracy
maximisation with cost as a CONSTRAINT**, not a term traded against quality — and has **declined**
the rule change that would have let price compete directly, because that would be a departure from
the method. So `select` keeps `max(feas, key=(c.quality, -c.cost_gpu_s))`.

**THE LIMITATION, in its strongest form.** This arm **cannot express a graded trade of price
against quality**. Cost is a tie-break on a **continuous** quantity, and a tie-break on a
continuous quantity **never fires**: `0.4286` and `0.3963` are not equal, so D2 wins whatever
RECENT costs. Price reaches a decision only through **feasibility** — that is, only when D2 is
SLO-infeasible and RECENT is not.

**That is a statement about this harness's expressible range, not about this method**, and it is
established from **two independent directions by two different mechanisms**:

1. **Here.** The lexicographic rule above, confirmed inert under D137 item 3: substituting the
   committed measured quality table for the ordinal constants moved **0 decisions at 8, 16 and 32
   devices**, because the selection consumes only the ORDER of the quality values and both tables
   share it.
2. **`cascade-routing`.** A method whose objective **does** price quality against cost directly,
   `quality - lambda * cost`, chooses the cheap option at **every** opportunity at its **minimum**
   lambda. Its trade is expressible in principle and saturated in practice.

**Two published arms, two entirely different selection mechanisms, neither able to express a graded
price-quality trade in this harness.** Recorded in both cards, because a reader of either alone
would reasonably attribute the flatness to that method.

**What this means for reading any eco-llm result.** A result showing that cheapening a
representation does not change eco-llm's selections is **not** evidence that price does not matter.
It is evidence that this rule consults price only after quality has already decided. The
D135 token reconciliation moved 3 decisions at 16 devices precisely because it changed
**feasibility**, which is the one channel price has.
