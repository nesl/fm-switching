<!-- StudyB-baselines. Written for a reviewer: everything faithful to the original is marked FAITHFUL, everything we changed is marked ADAPTATION with its reason. -->
# Tuned vLLM engine — our own measurement, **under-specified by the record**

**Files.** `tuned_engine.py`.

## The problem, checked against the repository

The task names this baseline as "the best engine configuration from **StudyE10c / E10e**
(priority + step budget + long-prefill threshold)". Three findings:

1. **StudyE10e does not exist.** There is no `reports/study_e10e*.md` and no StudyE10e row in
   `research/EXPERIMENTS.md`; the registry contains only StudyE10a, E10b, E10c and E10d.
2. **StudyE10c's verdict is that no engine setting helps.** It tested **E0** (vLLM 0.31.0
   default), **E1** (`--scheduling-policy priority`), **E2** (`--max-num-batched-tokens 2048`)
   and **E4** (E1 + E2), and found them "identical to E0 in 12 / 12 comparable ladders"; the
   levers "cost none without recall". So the best MEASURED configuration is indistinguishable
   from the default.
3. **The long-prefill threshold was never run.** StudyE10d lists
   `--long-prefill-token-threshold` (default 0) among untested levers.

## What this module therefore does

- Exposes exactly the four configurations a committed study measured (E0, E1, E2, E4), with their
  flags and the study that measured them.
- Records what was NOT run: E3 (512 tokens, dropped by the user's trim in E10c) and the
  long-prefill threshold.
- Sets `BEST_MEASURED = "E0"` with the reason attached, and **raises** on any other name — so
  asking for `"E10e-best"` fails loudly rather than producing a number no measurement supports.

## Mapping

It decides only `engine_config`; everything else takes the documented defaults, which isolates
the engine lever from the scheduling one.

## Open question for the user

Either StudyE10e is planned and this baseline should wait for it, or the intended baseline is
"E10c's best measured configuration", which is the **default engine** — in which case the tuned
engine and `naive.always-cloud-fcfs` differ only in name. **This needs a decision and is not
something to resolve by guessing.**
