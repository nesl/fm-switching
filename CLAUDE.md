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

## After any task

1. Update the `research/EXPERIMENTS.md` row (verdict, status).
2. Append a row to `results/INDEX.md`.
3. Update the last-updated date in `research/STATUS.md`.
4. Stop and ask the user to commit with a scoped file list.

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

---

## Git rules (read-only from CC)

- CC may run read-only git commands: `git rev-parse HEAD`, `git log`, `git status`, `git diff`.
- CC must NOT run `git add`, `git commit`, `git push`, or any history-altering command.
- Use filesystem `mv` for renames (tracked by git as rename + modify on next commit).
- Always stop and ask the user to commit at the end of a session.
