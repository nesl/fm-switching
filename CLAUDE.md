# FM-switching — CLAUDE.md

Claude Code context and conventions for this repository.

---

## Project overview

FM-switching studies state-management strategies for edge-cloud LLM orchestration. The two main tracks are:

1. **Simulator** (`simulator/`) — latency-hiding (LH) policies, MPC/SSM/RL routing, cost model.
2. **Accuracy experiments** (`experiments/`) — EgoSchema benchmark to measure how context representation affects task quality at the edge reasoner.

---

## Naming schema

### Scripts — named by FUNCTION, no device suffix, no ad-hoc numbers

| canonical name | role |
|---|---|
| `experiments/premise_egoschema.py` | helper module — shared primitives (imported by all other experiment scripts) |
| `experiments/context_inertia.py` | helper module — model loading, VLM/LLM inference, TTFT timing |
| `experiments/representation_frontier.py` | **canonical accuracy runner** — 500-clip EgoSchema, `--model qwen7b|smollm2` |
| `experiments/frame_sweep.py` | frame-count sweep (accuracy vs N frames) |
| `experiments/representation_sweep_n150.py` | historical 150-clip sweep (n=150 predecessor, kept for lineage) |
| `experiments/inertia_profile.py` | **canonical inertia profiler** — re-prefill latency vs token count, `--model --device` |
| `experiments/_provenance.py` | provenance stamp utility — embed `_provenance` in result JSONs |
| `experiments/memory_loading.py` | model cold/warm load timing |
| `experiments/tensorrt_int8.py` | TensorRT INT8 quantization experiment |
| `simulator/cost_model.py` | shared cost parameters; imports frontier/inertia JSONs at load time |

Device-dependent scripts are shared and take `--device` (never put device in the script name).

### Results — `<function>_<model>.json` or `<function>_<model>_<device>.json`

| pattern | when | example |
|---|---|---|
| `frontier_<model>.json` | device-independent accuracy (A6000 is the accuracy box) | `frontier_smollm2.json` |
| `frontier_<model>_perquestion.json` | per-question checkpoint arrays | `frontier_qwen7b_perquestion.json` |
| `framesweep_<model>.json` | frame-count sweep | `framesweep_qwen7b.json` |
| `inertia_<model>_<device>.json` | device-dependent latency curve | `inertia_smollm2_jetson.json` |
| `premise_<model>_<tag>.json` | pilot / premise validation | `premise_qwen7b_n150.json` |

**Model slugs:** `qwen7b` · `smollm2`  
**Device slugs:** `a6000` · `jetson` · `a6000`

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

## cost_model.py — MODEL knob and loading convention

`MODEL = "smollm2"` at the top of `simulator/cost_model.py` is the single global knob.
Change it to switch the entire simulation to a different model. Valid: `"smollm2"` | `"qwen7b"`.

`MODEL` drives three quantities at import time:

| data | source | fallback |
|---|---|---|
| QUALITY, EFFECTIVE_TOKENS | `results/frontier_<MODEL>.json` | hardcoded smollm2 measured values |
| KV_MB_PER_TOKEN | `_KV_MB_PER_TOKEN_BY_MODEL[MODEL]` lookup | — (dict always present) |
| Edge inertia curve | `results/inertia_<MODEL>_jetson.json` | linear FP16 prefill rate |
| Server inertia curve | `results/inertia_<MODEL>_a6000.json` | linear CLOUD prefill rate |

Both tiers use the same `MODEL` by default (keeps quality tier-independent).
A commented heterogeneous-tier block in cost_model.py documents how to enable per-tier model overrides and explains the confound that introduces.

Drop any schema-named JSON into `results/` and re-import to activate; no code change needed.

---

## Git rules (read-only from CC)

- CC may run read-only git commands: `git rev-parse HEAD`, `git log`, `git status`, `git diff`.
- CC must NOT run `git add`, `git commit`, `git push`, or any history-altering command.
- Use filesystem `mv` for renames (tracked by git as rename + modify on next commit).
- Always stop and ask the user to commit at the end of a session.

---

## Box roles

| box | role | primary scripts |
|---|---|---|
| **A6000** (this box) | Accuracy / representation experiments | `representation_frontier.py`, `frame_sweep.py`, `premise_egoschema.py` |
| **Jetson AGX Orin** | Edge inertia profiling | `inertia_profile.py --model smollm2 --device jetson` |
| **A6000** | Server inertia profiling | `inertia_profile.py --model qwen7b --device a6000` |

Result JSONs produced on other boxes follow the same naming schema and are committed from those boxes.
