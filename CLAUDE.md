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

**4. Definition audit.**
For every named object the experiment uses (win-10, sum-200, full, a "turn", a "session", reachability), state the concrete definition used in this run — token counts, unit of measurement, threshold values — and verify it matches the definition used in prior committed experiments. Report any name used with two different definitions across experiments. *(Motivating failure: E30 defined win-10 as 400 tokens; E32 measured win-10 as 7,117 tokens — same name, 17× different token counts, no reconciliation.)*

**5. Claim linkage.**
State which claim in `research/CLAIMS.md` and `research/FORMULATION.md` each headline result bears on, and whether it supports, weakens, or does not speak to that claim. If a measured quantity does not map to any claim, say so — that is a signal the experiment may be measuring the wrong thing. If the experiment measures an object that `research/FORMULATION.md` explicitly scopes out (e.g., KV transfer between tiers running different-sized models, per §Scoping "KV portability"), stop and flag it rather than reporting it as a result. *(Motivating failure: E31 Part D measured KV-cache transfer payloads; FORMULATION.md §Scoping states cross-architecture KV transfer is out of scope — the measurement was inapplicable to our setting.)*

**6. Proxy validity.**
Where a signal is used as a proxy for something else (an application state used as a network state, a caption count used as a turn count), state the proxy explicitly, state what it actually measures, and state whether it is valid for the claim. If the proxy is known to be questionable, it may not be used for a headline conclusion; report it as a limitation and mark the affected analysis as unvalidated. *(Motivating failure: E31 Part C derived reachability from State=D/I, an application download-activity flag, not a radio link state; the report noted the proxy was questionable and used it anyway for the headline predictability analysis.)*

---

## After any task

1. Run the **Results consistency check** (above) and record the outcome before writing conclusions.
2. Update the `research/EXPERIMENTS.md` row (verdict, status, consistency_check).
3. Append a row to `results/INDEX.md`.
4. Update the last-updated date in `research/STATUS.md`.
5. Stop and ask the user to commit with a scoped file list.

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

## Git rules (read-only from CC)

- CC may run read-only git commands: `git rev-parse HEAD`, `git log`, `git status`, `git diff`.
- CC must NOT run `git add`, `git commit`, `git push`, or any history-altering command.
- Use filesystem `mv` for renames (tracked by git as rename + modify on next commit).
- Always stop and ask the user to commit at the end of a session.
