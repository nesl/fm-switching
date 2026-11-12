<!-- StudyB-baselines. Our own measured configuration, not an external paper.
DECIDED BY THE USER 2026-11-12 after StudyE10e-partial-prefill landed: tuned-engine = E10e's P1. -->

# Tuned vLLM engine — our own measurement — **= StudyE10e's P1**

**Files.** `tuned_engine.py`. **Experiment:** C-mixed.

**Decision (user, 2026-11-12).** The tuned engine is **StudyE10e's P1**:
`--long-prefill-token-threshold 1024`, the **default** step budget (8,192), **FCFS**.

## The three studies behind it

| study | configurations tested | verdict |
|---|---|---|
| **StudyE10c-engine** | E0 (vLLM 0.31.0 default), E1 (`--scheduling-policy priority`), E2 (`--max-num-batched-tokens 2048`), E4 (E1 + E2) | **No engine setting restores capacity.** "Identical to E0 in 12 / 12 comparable ladders"; the levers "cost none without recall". Cold K1 recall needs isolation or admission control, not scheduler tuning. |
| **StudyE10d-blocking** | V1 PNG / V2 JPEG q88 / V3 text-only, token-matched | **The LM prefill is the unsplittable unit.** All three variants block on both engines; held requests are released at the cold first token. Body size and the vision encoder only lengthen the window; the ~12.6k-token prefill alone holds episodic scoring. Named `--long-prefill-token-threshold` (default 0) as an **untested** lever. |
| **StudyE10e-partial-prefill** | P1 (threshold 1024), P2 (512), P3 (1024 + priority) | **Pre-registered verdict: no config removes the interference.** All three hold C0 capacity at the 40 % ladder top with no loss, and all three collapse to **< 10 %** under cold recall (C1) and under KV-host + cold recall (C4) — five ladder levels below their own C0. |

### StudyE10e's capacity table (episodic N = 1, p99 ≤ 0.45 s)

| config | C0 (no recall) | C1 (cold r 0.05) | C4 (KV-HOST k 8 + cold r 0.1) | levels below own C0 | removes interference? |
|---|---|---|---|---|---|
| P0 default | **40 %** (top) | < 10 % (2.646 s) | < 10 % (4.710 s) | 5 | — (control) |
| **P1 threshold 1024** | **40 %** | < 10 % (**2.124 s**) | < 10 % (**3.499 s**) | 5 | **no** |
| P2 threshold 512 | **40 %** | < 10 % (1.978 s) | < 10 % (3.274 s) | 5 | **no** |
| P3 1024 + priority | **40 %** | < 10 % (2.154 s) | < 10 % (3.847 s) | 5 | **no** |

## Why P1 — and why P1 rather than P2 or P3

P1 buys a real tail-latency improvement at **no capacity cost**:

- episodic p99 **−19–25 % at C1** (2.65 → 2.12 s) and **−18–30 % at C4** (4.71 → 3.50 s);
- **no C0 capacity loss** in any config (40 % kept; p99 at 40 % 0.364–0.385 s vs P0's 0.383 s);
- the cap demonstrably works: StudyE10e sees held requests released **1.0–1.8 s before** the cold
  first token, against 0.00 s at P0;
- no starvation and no preemptions in any config.

**Its measured costs, in full.** The cost falls on **cold** recall, and P1 is the only one of the
three that spares **warm** recall:

| config | cold TTFT p50, C1 | cold p99, C1 | cold p50, C4 | cold p99, C4 | warm append p50, C4 | warm escalation p50, C4 |
|---|---|---|---|---|---|---|
| P0 | 3.899 s | 5.582 s | 4.449 s | 6.942 s | 0.318 s | 0.391 s |
| **P1** | 4.075 (**×1.05**) | 6.248 (**×1.12**) | 4.944 (**×1.11**) | 7.880 (**×1.14**) | 0.323 (**×1.02**) | 0.396 (**×1.01**) |
| P2 | 3.972 (×1.02) | 6.318 (×1.13) | 5.064 (×1.14) | 7.910 (×1.14) | 0.435 (×1.37) | 0.510 (×1.30) |
| P3 | 4.032 (×1.03) | 6.249 (×1.12) | 5.468 (×1.23) | 8.404 (×1.21) | 0.488 (×1.53) | 0.819 (**×2.09**) |

So: **P1 ×1.02 / ×1.01 on warm recall, against P2's ×1.37 / ×1.30 and P3's ×1.53 / ×2.09** (P3's
priority puts warm requests behind episodic ones and doubles escalation). That is the whole case
for P1 over its siblings, and it is the reason the decision is defensible even though cold-recall
p99 rises 12–14 %.

## What this baseline is NOT

**It does not restore capacity.** StudyE10e's pre-registered verdict stands: *no* config removes
the cold-recall interference, and P1 is five ladder levels below its own C0 under recall. This
baseline is the best measured **tail-latency** configuration at no capacity cost — which is what a
serving reference should be — not a solution to the interference. StudyE10c's conclusion holds:
cold recall needs isolation or admission control, which is what the *scheduling* baselines and our
scheduler are for.

## What the module exposes

- All **seven** measured configurations: `E0, E1, E2, E4` (StudyE10c) and `P1, P2, P3`
  (StudyE10e), each with its flags and the study that measured it.
- `TUNED = "P1"` (the decision) and `BEST_MEASURED = "E0"` (the best under E10c/E10e's *capacity*
  rule), each with its own recorded reason, so the two senses are never conflated.
- What was **not** run or does not exist: E3 (dropped by the user's trim in E10c);
  `--max-num-partial-prefills` and `--max-long-partial-prefills`, which **do not exist in vLLM
  0.31.0** (E10e §0 flag check); `--long-prefill-token-threshold-adaptive`, supported but
  deliberately unused by E10e because its floor weakens the cap in exactly the C1 case; and the
  two combinations E10e names as a caveat.
- **The guard is kept**: any configuration name no committed study measured **raises**.

## The caveat StudyE10e states, carried here

E10e locates the residual precisely: the cap applies only when another request is already in the
system at schedule time, and with async scheduling and an 8,192-token step the cold prefill's two
steps are usually taken alone. Its "not removable" verdict therefore covers its own controls plus
E10c's, **not** two documented 0.31.0 combinations it did not try:

- a smaller step budget together with the cap
  (`--max-num-batched-tokens 2048 --long-prefill-token-threshold 512`);
- `--no-async-scheduling`.

If either is measured and does better, `TUNED` is the single line to change.

## Hyperparameters and provenance

| name | value | from |
|---|---|---|
| `TUNED` | `P1` = `--long-prefill-token-threshold 1024`, default step budget, FCFS | user decision 2026-11-12 on StudyE10e's evidence |
| `BEST_MEASURED` | `E0` | StudyE10c + StudyE10e under the capacity rule |
| configuration flags | verbatim | each study's own configuration table |
| all costs quoted above | measured | StudyE10e §3, §4, §5 |
