# FM-switching — CLAUDE.md

Claude Code context and conventions for this repository.

---

## Project overview

FM-switching studies representation-aware warm-state continuity for mobile FM agents: session state can be held as full-replay, window-10, summary-80, or summary-200, differing in reconstruction cost and in fidelity. Context Inertia has a physical component (transfer and reconstruction latency, which grows with context length) and a semantic component (cheaper representations discard task-relevant information in a workload-dependent way). The current stage is fidelity audit complete under two models and cost profiling done on A6000 and RTX 3090 Ti; the next gate is a trace-driven simulator showing joint representation × placement × timing beats decomposed policies under a quality SLO.

---

## Before any task

1. Read `research/STATUS.md` to understand the current stage and open gates.
2. Find or request an E-id in `research/EXPERIMENTS.md`. If no matching row exists, stop and ask before proceeding.

---

## Mechanism verification (mandatory before any sweep)

Run this protocol for every experiment that tests a causal claim, **completed and recorded before the full sweep runs and before any conclusion is written**. If any step fails, stop and report the failure; do not run the sweep and explain it afterwards.

Precedent: E36, E36b, and E36c all passed the six-check consistency protocol and all produced nulls that were later traced to the mechanism under test being absent from the simulation. Maintenance work was never charged to the accelerator budget, so the representation-dependent maintenance cost — the cost the experiment exists to measure — contributed zero to every policy comparison. A quantity that is correctly and consistently zero passes every consistency check. This protocol is the only check that can catch that failure mode.

Earlier instances of the same failure: E31 measured KV-transfer payloads in a setting where the formulation (FORMULATION.md §Scoping) states KV cannot move between heterogeneous tiers; E24b compared policies whose action spaces did not contain each other; E32 and E34 measured catch-up latency with the delta already in cache. In each case the numbers were internally consistent and the experiment did not test the claim.

---

**Step 0 — Ask what would invalidate this run, BEFORE starting it.**

Before a run begins, write down what would make its result uninterpretable, and check each one. Is the comparator about to change? Is a default about to be restored? Does the output of a run you depend on key into your analysis? Does the mechanism have a reachable path at this size and in this regime? **It costs about a minute whether the answer is "nothing" or "wait", and the asymmetry is the point: a minute spent before, against a run re-done or a null explained after.**

*Motivating failures, which run both ways:* a grep for whether `DEFAULTS["session_action"]` was ever applied came back **clean** and cost a minute. A sequencing question came back **"wait"** and saved a pressure run from straddling three separate changes to the bar. A positive control on `cascade-routing`, the only price-responsive arm in a run, found that it **was not price-responsive** - in time to fix it rather than in time to explain a null.

**Step 1 — State the causal chain.**

In one paragraph, in your own words, write the chain of cause and effect the experiment is testing, with each link traced to a specific claim in `research/FORMULATION.md`. Write the mechanism, not the hypothesis: not "maintenance_aware will outperform always_full" but "if maintenance costs are representation-dependent (FORMULATION.md §refresh), then a policy that accounts for those costs will prefer a cheaper representation when capacity is constrained, reducing evictions, and the resulting higher admission rate will increase the fraction of queries meeting both the latency and quality SLO." If you cannot write this chain with every link grounded in the formulation, stop and ask before proceeding.

---

**Step 2 — Instantiate each link.**

For every link in the causal chain from Step 1, name the specific simulation or measurement quantity that implements it, give its value in this run (or its range across conditions), and show evidence that the quantity is **non-zero and varies across the conditions where the claim says it should vary**.

For each link, fill in this table:

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence |
|---|---|---|---|---|

A link whose quantity is zero, constant, or absent from the simulation means the experiment cannot test that part of the claim. Mark such a link **ABSENT** or **CONSTANT**. Any ABSENT or CONSTANT entry is a stopping condition: do not proceed to the sweep.

For every link, name the **read** that consumes the implementing quantity, not merely the place it is set. Give the file and line of the code that *uses* the value to change a decision. A quantity that is written and never read is **ABSENT**, and is a stopping condition exactly as a zero or a constant is.

*Motivating failure (the write-only field):* `desired_tier` was set by two actions that were dispatched by name, counted in `self.counts`, and handled by a named branch in the coordinator, so every surface sign said the mechanism was live. Across all of live2 it had three references: one declaration and two writes, and no read. `RecallAction.representation` had the same shape until `e924005`. A write-only field is non-zero, varies by arm and by condition, and is instrumentable, so it satisfies Step 2 as written while implementing no causal link at all; the Step 4 negative control also passes, because disabling the writes correctly collapses to the null.

*Motivating failure (E36, E36b, E36c):* The causal chain required that refresh cost vary by representation and be charged to the accelerator budget on each turn. `EDGE_SUM200_UPDATE_MS = 5822` was defined, but `refresh_ms(fidelity, workload)` returned 0.0 for all fidelities except sum200, and sum200 was never admissible for LoCoMo (the primary workload) because `Q(sum200, locomo) = 0.12 < q_min = 0.20`. As a result the accelerator budget was never the binding resource in any LoCoMo run. The causal link "maintenance cost → accelerator constraint → admission decision" was absent. The consistency protocol never saw this because the zero was correctly and consistently zero.

---

**Step 2b — Confirm the switch reaches a decision.**

Before scoring any A-versus-B comparison, run both conditions on one cell and diff the decision logs. Report the number of differing decisions and the first one. If the logs are identical, the comparison has not been run: the result is an **ABSENT LINK**, never a negative. Confirm also that each switch arrived at the object under test with its declared type and value, not merely that it was passed.

This costs one cell and is run **before** the sweep, not after a suspicious null.

*Motivating failure (five plumbing faults in three nights), every one found only after a null had been produced and nearly written up:* a `--candidate` parser turned `mu_mode=scarcity` into a literal key; `make_arm` silently discarded kwargs so `c_inflight=8` returned the default arm; a field declared `int` was coerced to `bool`, turning 2 into 1; B2's `z[RC]` reached 543.58 and no decision; RCprio never fired even at a slack threshold equal to the entire deadline.

---

**Step 3 — Trace one representative unit.**

Paste an instrumented trace of one epoch, one session, or one request — whichever is the unit of the experiment — showing every cost and constraint charged, what bound it, and the resulting outcome. The trace must be readable by a person checking the arithmetic by hand. Include:

- All input quantities (context length, fidelity chosen, quality score, TTFT)
- All costs charged to each budget (KV bytes used, accelerator ms charged)
- Which budget bound the decision (KV, accelerator, or neither)
- The per-unit outcome (both_met, latency_miss, quality_miss)

If you cannot produce this trace — because the quantities are not instrumented, because the unit is not recoverable, or because the costs are aggregated before they can be inspected — the simulation is not instrumented to the level needed to verify the mechanism. Add instrumentation before running the sweep.

---

**Step 4 — Run a negative control.**

Artificially disable the mechanism under test and confirm the result collapses to the null:

- If the claim is that accelerator cost drives policy differentiation: set all `refresh_ms` to zero and confirm all policies converge to the same both_met.
- If the claim is that KV memory pressure drives policy differentiation: set `kv_cap` to infinity and confirm all admission-based policies converge.
- If the claim is that quality fidelity variation drives policy differentiation: set all `Q_TABLE` values equal and confirm quality-based policies converge.

If the result does **not** change when the mechanism is disabled, the mechanism is not driving the result. Report the control outcome alongside the main result and identify what is actually driving the difference.

This control need only run on a single representative cell (one workload, one fleet size, one budget). Document the cell and the result.

---

**Step 5 — Name the alternative explanation.**

State at least one alternative mechanism that would produce the same headline result and what in the data distinguishes it from the claimed mechanism. If nothing distinguishes them, say so and stop.

*Example:* "maintenance_aware outperforms always_full" could be produced by (a) maintenance-cost-aware scheduling reducing evictions [the claimed mechanism], or (b) maintenance_aware coincidentally picking the lowest-KV admissible fidelity regardless of maintenance cost, which footprint_ranked also does [the alternative]. If both explanations make the same predictions on the sweep, the experiment cannot distinguish them.

---

**Rules.**

**Rule 1 — Null results from absent mechanisms are not findings.** A null result may not be reported as a finding until mechanism verification has passed. A null from an experiment where the mechanism was absent, zero, or outside the tested parameter range is an artifact of the experimental design, not evidence that the mechanism does not exist. It must be labelled as such in the report. Three prior experiments — E36, E36b, and E36c — produced nulls under this condition and are cited here as precedent; their EXPERIMENTS.md entries are marked NOT PERFORMED.

**Rule 2 — Null results must be classified.** When an experiment produces a null, the report must state explicitly which of the following applies:

- **Real negative:** the mechanism was present (Step 2 passed for all links, Step 4 showed the control changed the result), it operated as specified, and it did not produce the claimed effect. This is a settled finding.
- **Inconclusive:** the mechanism did not operate as specified. The experiment has not tested the claim; this is not a settled finding, it is a design failure. State **which** of the following applies, because the diagnostic and the remedy differ and only the last is a finding about the policy:
  - **cancelled by geometry** — the quantity is alive and cancels between the compared branches, so it cannot affect the difference. *(B2's deficit; spec 5.3 state value, non-zero in 96.6 percent of branches and exactly equal across them in 12,898 of 12,898 candidates.)*
  - **unexpressible** — the mechanism fires but the harness discards the channel it acts through. *(the action `order` field; `desired_tier`.)*
  - **unscorable** — the objective cannot see the quantity the mechanism changes. *(a 12 to 25 percent GPU-second spread moving ΔJ by zero to nine decimal places.)*
  - **unexercised** — the mechanism is reachable but no condition in the run reaches it. *(RELOAD is offered only at HOST-WARM and no recall reached HOST-WARM; **E36, E36b and E36c were this case**.)*
  - **fired and did not help** — the mechanism operated and produced no effect. **This is the only one that is evidence about the policy**, and it is still not a settled negative unless Step 4 showed the control changed the result.

These two outcomes are not the same and must not be reported the same way.

---

## Results consistency check (mandatory before writing conclusions)

Run this protocol for every experiment that produces numbers, **before** writing any conclusion or filling in the EXPERIMENTS.md verdict. Six checks, in order. Record the results of each check in the experiment's report; if a check fails, stop and surface the discrepancy rather than proceeding to conclusions.

**1. Cross-check against committed measurements.**
For every quantity this experiment measures that has been measured before, locate the prior committed value (primary index: `results/INDEX.md` and `research/EXPERIMENTS.md`; secondary: `results/cost/cost_matrix.csv`, `reports/phase1_cost_profiling.md`). Produce a table:

| quantity | this run | prior run | source of prior | ratio | agree/disagree |

Any disagreement greater than 2× must be investigated and explained before conclusions are written. If the discrepancy cannot be explained, stop and report it rather than choosing one value. *(Motivating failure: E30 used win-10 = 400 tokens; E32 measured win-10 = 7,117 tokens — 17× disagreement on the quantity that determines the memory-vs-accelerator conclusion.)*

**2. Physical plausibility check.**
For every latency, throughput, or size measurement, state the implied rate (tokens/s, bytes/s, GB) and compare it against the committed cost curves in `results/cost/cost_matrix.csv` and `reports/phase1_cost_profiling.md`. Flag any result implying a rate more than 2× faster than the corresponding measured rate. A result faster than the committed curves is a caching artifact or an instrumentation error, not a finding. *(Motivating failure: E32 Part B warm-append at 89 ms for a 3,010-token delta implies ~34,000 tok/s; committed A6000 cold prefill is ~7,100 tok/s — 4.8× discrepancy, unchecked.)*

**3. Distribution sanity.**
Where a median is reported over multiple items, also report the spread (min, max, IQR, or all per-item values). Flag any case where values agree to more precision than the inputs vary — e.g., medians across sessions of different lengths that agree to three decimal places. Constants appearing where distributions are expected indicate short-circuiting or caching. *(Motivating failure: E32 sum200 full-regen = 8.766 s identical to three decimal places across ten conversations of differing lengths at every N.)*

A constant where a distribution is expected is only the most visible of three shapes. Also flag:

- **an artefact spread** — values that differ across arms by a credible margin while deriving from a quantity that cannot carry the meaning claimed. Before trusting a spread, state what the values *are* and confirm they can mean what the column says.
- **a real effect averaged into undetectability** — a population mean below its own noise floor that conceals a large effect on a stratum. Where an effect is expected to be concentrated, report the stratum and the mixing weight beside the mean.

**A constant advertises breakage; a plausible spread does not**, and an averaged-out effect reads as an equivalence, which is wrong in both directions at once. *(Motivating failures: an accuracy column spread 0.0289 to 0.2143 across arms while every cloud answer was a placeholder `"X"` that never matched a gold letter, so the spread tracked only how many questions each arm delivered on time and ranked the arms backwards; and a +1.18 pp population gap with a CI including zero concealed +17.5 pp on the 11.5 percent stratum where the recent window misses the evidence.)*

**4. Definition audit.**
For every named object the experiment uses (win-10, sum-200, full, a "turn", a "session", reachability), state the concrete definition used in this run — token counts, unit of measurement, threshold values — and verify it matches the definition used in prior committed experiments. Report any name used with two different definitions across experiments. *(Motivating failure: E30 defined win-10 as 400 tokens; E32 measured win-10 as 7,117 tokens — same name, 17× different token counts, no reconciliation.)*

**5. Claim linkage.**
State which claim in `research/CLAIMS.md` and `research/FORMULATION.md` each headline result bears on, and whether it supports, weakens, or does not speak to that claim. If a measured quantity does not map to any claim, say so — that is a signal the experiment may be measuring the wrong thing. If the experiment measures an object that `research/FORMULATION.md` explicitly scopes out (e.g., KV transfer between tiers running different-sized models, per §Scoping "KV portability"), stop and flag it rather than reporting it as a result. *(Motivating failure: E31 Part D measured KV-cache transfer payloads; FORMULATION.md §Scoping states cross-architecture KV transfer is out of scope — the measurement was inapplicable to our setting.)*

**6. Proxy validity.**
Where a signal is used as a proxy for something else (an application state used as a network state, a caption count used as a turn count), state the proxy explicitly, state what it actually measures, and state whether it is valid for the claim. If the proxy is known to be questionable, it may not be used for a headline conclusion; report it as a limitation and mark the affected analysis as unvalidated. *(Motivating failure: E31 Part C derived reachability from State=D/I, an application download-activity flag, not a radio link state; the report noted the proxy was questionable and used it anyway for the headline predictability analysis.)*

**7. Validate the control, not only the result.**
In any before/after or arm-versus-baseline comparison, cross-check the **control** arm's own numbers against its committed values before reading the comparison. A broken control passes every check applied to the treatment, because the treatment is fine. Include a **positive control**: a known-good committed arm must pass the check being applied. If it fails, **the check is broken, not the arm**. An impossible failure and an impossible success are equally diagnostic, and a reviewer watching only for implausible *results* will catch neither. *(Motivating failures: a before-condition gave dashcam 0.0821 and 0 recalls against that arm's committed 0.8164 and 14 of 35 — a "before" condition that destroys the arm is not a before condition — and it was caught by the magnitude, not the method, so a subtler break would have passed; and a legality pass reported 2,834 to 3,000 illegal actions for every arm including the committed `b7` control, which cannot be illegal.)* **The general shape:** a comparator planning at one price while charged another, and a broken control arm, are the same blindness — a side of the comparison that is never audited. Arm-versus-arm checking cannot see either, because every arm is compared against the same unexamined bar.

---

## After any task

1. Run the **Mechanism verification** (above) and record Steps 1–5 in the experiment's report **before the sweep runs**.
2. Run the **Results consistency check** (above) and record the outcome before writing conclusions.
3. Update the `research/EXPERIMENTS.md` row (verdict, status, consistency_check, mechanism_verification).
4. Append a row to `results/INDEX.md`.
5. Update the last-updated date in `research/STATUS.md`.
6. Stop and ask the user to commit with a scoped file list.

---

## Layout and naming schema

### Directory structure

```
results/<purpose>/          — all result files; never outside this tree
experiments/<purpose>/      — scripts, organized by purpose
figures/<purpose>/          — publication figures
plots/<purpose>/            — plot scripts
```

**Purposes:** `fidelity` · `cost` · `orchestration` · `casestudy` · `archive`

### Result file naming

Host-specific files (produced on one tier) carry the tier slug in the name:

```
<slug>_<model>_<tier>.json          # device-specific
<slug>_<model>.json                  # device-independent (accuracy box is A6000)
<slug>_<model>_perquestion.json      # per-question arrays
```

Merged files (combining multiple tiers) carry **no** tier identifier:
```
cost_matrix.csv                      # tier is a column
```
Track merged outputs in `research/EXPERIMENTS.md` (E-id row, "output" column).
The two existing reports (`reports/phase0a_multimodel_audit.md`, `reports/phase1_cost_profiling.md`) keep their historical filenames.

**Never** use `phaseN`, `sprintN`, or ad-hoc numbers in any path or filename.

### Model slugs

| slug | model ID |
|---|---|
| `qwen7b` | Qwen/Qwen2.5-7B-Instruct |
| `smollm2` | HuggingFaceTB/SmolLM2-1.7B-Instruct |
| `qwen3b` | Qwen/Qwen2.5-3B-Instruct |
| `qwenvl3b` | Qwen/Qwen2.5-VL-3B-Instruct (or fine-tuned variant) |
| `qwenvl7b` | Qwen/Qwen2.5-VL-7B-Instruct |
| `mistral7b` | mistralai/Mistral-7B-Instruct-v0.2 |

### Device slugs

| slug | hardware | host |
|---|---|---|
| `a6000` | NVIDIA RTX A6000 | flash (GPU 1) |
| `rtx3090ti` | NVIDIA GeForce RTX 3090 Ti | flash (GPU 0) |
| `jetson_orin` | Jetson AGX Orin | separate SSH host |
| `h100nvl` | NVIDIA H100 NVL | sn4622120321 (shared; GPU 3 preferred — see `research/HOST_H100.md`) |

### Box roles

| box | role | primary scripts |
|---|---|---|
| **flash / A6000** | Fidelity experiments; server-tier cost profiling | `experiments/fidelity/`, `experiments/cost/cost_profile.py --tier a6000` |
| **flash / RTX 3090 Ti** | Edge-tier cost profiling | `experiments/cost/cost_profile.py --tier rtx3090ti` |
| **Jetson AGX Orin** | Device-tier cost profiling | `experiments/cost/cost_profile.py --tier jetson_orin` |

Result files from each host are committed from that host.

---

## Provenance convention

Every result JSON written by an experiment script must include:

```json
"_provenance": {
  "git_commit": "<sha or 'pre-provenance'>",
  "script": "representation_frontier.py",
  "model": "smollm2",
  "device": "nvidia_rtx_a6000",
  "n": 500,
  "timestamp": "2026-06-10T22:12:00.000000"
}
```

Use `from _provenance import stamp` and call `stamp(script=..., model=..., device=..., n=..., args=args)` at the end of each run, then embed the returned dict as `result["_provenance"]`.

Existing JSONs written before this convention was adopted carry `"git_commit": "pre-provenance"` with a human note.

---

## Shared traceability log

**`results/INDEX.md`** is the cross-box correctness trail. It maps every result file to its script, model, device, n, headline finding, and old name. Update it whenever a new result is produced.

`MEMORY.md` at the repo root is per-box local context (gitignored) — CC's working memory for the current machine. It is NOT a substitute for INDEX.md.

---

## Rules

- **Result directories:** Do not create result dirs outside `results/<purpose>/`. If a purpose directory does not exist, check `research/EXPERIMENTS.md` first — the experiment may not yet have an E-id.

- **New datasets:** Do not propose new datasets or workloads. `research/GRAVEYARD.md` documents why candidates were closed. If a new dataset seems necessary, stop and describe the gap it would fill; do not implement.

- **Methodological changes** (dropping items, changing metrics, shortening contexts, changing the n, swapping models or baselines) must be flagged and discussed before being applied. Implementation fixes (bugs, wrong file paths, incorrect measurement procedures) may be applied directly and reported after.

- **Caching behaviour is a methodological parameter, not an implementation detail.** Any experiment measuring latency must state explicitly: whether prefix caching or any other cache was enabled; what was cached before measurement began; and whether repeated measurements of the same input could be served from cache. Warm and cold conditions must be labelled and must not be compared to each other without saying so. A number labelled "cold prefill" that was obtained with prefix caching enabled is not a cold prefill measurement.

---

## Citing results

- **A port's proofs must include that its characteristic decision occurs at least once.** Before a ported arm is scored, record the count of the decision kind that arm exists to make, and confirm it is non-zero. **The required well-formedness and fairness checks establish that an arm is legal and fairly treated; neither establishes that it does anything.** *(Motivating failure: a port passed BOTH required proofs perfectly - 0 illegal actions across 3,001 epochs and a fairness digest matching the committed control - while producing ZERO decisions of its characteristic kind, because its sufficiency proxy could never fire.)* **This is the port-side twin of Step 2b**, which requires the same of a switch: Step 2b asks whether a switch moved a decision, this asks whether an arm ever made its own. A reader meeting one should know the other exists.

- **Mark the register at the point of use**, not only where a number is derived: **observed count** against **constructed bound**; **applied locally** against **pushed and verified on origin**; **one traced unit** against **a full table**. A number in the wrong register is not a wrong computation and will survive every arithmetic check. *(Motivating failures: a worst-case construction reported as a census; "committed to `coordinator.py`" meaning written into the file and read as git-committed and pushed, which unblocked a session against a change that was not on origin; and a single category's delta generalised to a direction, when across all eight categories the cheaper representation was better on four, led by `location_trace` at +17.2 pp.)*

- **Before citing any result, check its status in `research/EXPERIMENTS.md`.**
- **Never cite or recompute from a result marked INVALID.**
- **Comparisons between arms must state whether input, stack and decoding match.**

## Git rules (read-only from CC)

- CC may run read-only git commands: `git rev-parse HEAD`, `git log`, `git status`, `git diff`.
- CC must NOT run `git add`, `git commit`, `git push`, or any history-altering command.
- Use filesystem `mv` for renames (tracked by git as rename + modify on next commit).
- Always stop and ask the user to commit at the end of a session.
