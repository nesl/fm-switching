# Pre-registration: the ENGINE-FLAG DIAGNOSTIC for rung 1's dashcam loss

**Written and committed BEFORE any cell of `results/orchestration/live2/frozen_test/runs/C5DIAG_CELLS`
is run, and before any number from such a cell is read.** Session C5-B, 2026-11-22, under the user
ruling of 2026-11-22 (addendum), item 3.

**This is a DIAGNOSTIC, never a headline.** The flag is SERVER-WIDE: it changes the engine for
every arm in the cells it is used for, so a cell run under it is not comparable with any committed
cell, and ADOPTING it would mean rerunning every arm. Nothing here is adopted, and no arm's code
changes for it. The committed server configuration is the one with NO extra flags.

---

## 1. What is being diagnosed

`c5_loss_split.json` (read-only, seeds 4 to 7) splits rung 1's dashcam loss. Monitor opportunities
NEVER SUBMITTED are 52 to 58 percent of all opportunities at rung 1 against 13 to 17 percent for
the base arm, and the dominant bucket is "C5's cap is shut AND a robot prefill is in flight" at
37.5 to 43.0 percent against 3.7 to 7.9. The cap closes because monitor first-token times cross
C5's 0.8 s trip. The engine-side question is therefore: **does a monitor request wait behind a long
robot prefill inside the engine, and does capping the long prefill's per-step token share stop
that?** This is layer 1 in the loss split's own language, upstream of the C5 attribution rule
(layer 2, `covex-v6-state-uo-c5attr`), and the two act on different quantities.

## 2. The engine facts, from the vLLM 0.31.0 source

The live server is **vLLM 0.31.0+cu129**, confirmed by the H100 from its venv METADATA, so these
facts are facts about the live server and not about a wheel in general.

| fact | source |
|---|---|
| the scheduler serves the **RUNNING** set first against a shared `token_budget`, then scans **WAITING** under `while token_budget > 0`, so an unthrottled long prefill can leave the waiting scan nothing | `v1/core/sched/scheduler.py` running scan at ~630, waiting scan after it |
| `long_prefill_token_threshold` defaults to **0 (disabled)** | `config/scheduler.py:80` |
| the threshold is forced to **0 when `num_running + num_waiting <= 1`**, so the cap vanishes when the long prefill is alone and costs nothing then | `v1/core/sched/scheduler.py:614-620` |
| the cap is applied **per request per step in BOTH scans**: `if 0 < long_prefill_token_threshold < num_new_tokens: num_new_tokens = threshold` | `v1/core/sched/scheduler.py:679-680` (running) and `:1110-1111` (waiting) |
| `SchedulerConfig.DEFAULT_MAX_NUM_BATCHED_TOKENS = 2048`, but a serving config raises it | `config/scheduler.py:42` |
| **`max-num-partial-prefills` DOES NOT EXIST in 0.31.0** (no occurrence anywhere in the source), which matches the committed StudyE10e s0 flag check recorded in `baselines/tuned_engine.py` NOT_RUN | source grep + `baselines/tuned_engine.py` |
| `long_prefill_token_threshold_adaptive` exists but is deliberately NOT used: its floor weakens the cap exactly when few requests wait | `config/scheduler.py:87-91`, StudyE10e's own reason |

**So the diagnostic uses exactly one flag: `--long-prefill-token-threshold N`.** A second flag is
not available in this engine version and none is invented.

## 3. The budget the live server actually resolves

The live launch command (`study_live2_pilot.start_server`, pinned to the ENG1C `DE_c38` flag list)
does **not** set `--max-num-batched-tokens`, so the engine resolves it. Committed server records
for the same engine version and the same base flag list report
**`max_num_batched_tokens = 8192`** (`results/cost/study_e10/e10e_run_meta_h100nvl.json`, every
server entry; also `baselines/tuned_engine.py` E0's description). **B = 8192.**

**Conditional, because the H100 verifies the launched argv:** if the launched server's own log
reports a resolved `max_num_batched_tokens` other than 8192, N is re-derived by the rule in section
5 with that B, and the cells are not run on the value below.

## 4. The monitor request is NOT 1,056 tokens, and this changes the derivation

The ruling's figure of "about 1,056 prompt tokens" is the **minimum**. Measured from the committed
rung-1 cell `v5-rules-2_n16_s4_1200s_h27_3t_L3_epg_rq30` (engine-reported `prompt_tokens`, 4,827
monitor requests, EP-G episodes of up to 21 frames):

| quantity | value |
|---|---|
| monitor prompt tokens, min | **1,056** |
| monitor prompt tokens, p50 | **3,760** |
| monitor prompt tokens, p99 and max | **7,140** |
| non-monitor prompt tokens, p50 / p90 / max | 1,393 / 14,591 / **26,660** |
| non-monitor uncached, p50 / p90 / max | 1,374 / 9,311 / 26,660 |

So "a monitor fits in a step beside a long prefill at B = 8192" cannot be met for every monitor at
once: 7,140 + N <= 8,192 forces N <= 1,052, which is below the smallest monitor. The achievable and
useful property is **ADMISSION**: the waiting monitor must be admitted in the same step, with
whatever chunk the budget leaves, instead of finding `token_budget` at zero.

Concurrency, measured on the prefill phase only (`[t_submit, t_first_token]`) in the same cells,
because that is the phase that spends the token budget:

| cell | robot prefill-phase concurrency p50 / p90 / p99 / max | decode-phase max |
|---|---|---|
| v5-rules-2 s4 | 1 / 3 / 11 / 13 | 9 |
| v5-rules-2 s5 | 1 / 3 / 7 / 10 | 9 |
| noc3 s4 (base) | 0 / 1 / 2 / 5 | 9 |

## 5. The pre-registered N, with the arithmetic

Let B = 8192 (resolved budget), D = 16 (token allowance for requests in decode, one token each;
measured maximum concurrent decode is 9), k = concurrent long prefill chunks.

A waiting monitor is admitted in a step iff `B - D - k*N >= 1`.

**Rule: N is the largest power of two that (a) is at least the minimum monitor prompt (1,056), so
the smallest monitor is never chunked, and (b) keeps a waiting monitor admissible at the measured
p90 robot prefill-phase concurrency k = 3.**

- N = 2048: 8192 - 16 - 3 x 2048 = **2,032 >= 1** -> admitted at k = 3; admission first fails at
  k >= ceil(8176 / 2048) = **4**.
- N = 4096: 8192 - 16 - 3 x 4096 = **-4,096 < 1** -> fails at k = 3 (it fails already at k = 2).
- N = 1024 (the committed tuned-engine P1) satisfies (b) up to k = 7 but **violates (a)**: 1,024 is
  below the 1,056-token minimum monitor, so even the smallest monitor is chunked.

**PRE-REGISTERED VALUE: N = 2048. Flag string, exactly as it must appear in the server's argv:**

```
--long-prefill-token-threshold 2048
```

Monitor chunking under it: the smallest monitor (1,056) in 1 step, the p50 (3,760) in 2, the
largest (7,140) in 4.

## 6. What it costs the long prefill, stated before the run

A long prefill is capped at 2,048 tokens per step, so a 27k-token prefill (the measured maximum
non-monitor prompt is 26,660) needs **ceil(26660 / 2048) = 14 steps at best**, against
ceil(26660 / 8192) = **4** unthrottled: at least **10 extra scheduler steps**, plus whatever other
requests' chunks are interleaved. Committed evidence on the same lever at N = 1024 (StudyE10e P1,
`baselines/cards/tuned_engine.md`): cold recall TTFT p99 **x1.12 to x1.14**, warm recall barely
touched (append x1.02, escalation x1.01), episodic p99 **down 18 to 30 percent**, no C0 capacity
cost. StudyE10e's pre-registered verdict, which stands and is not re-litigated here: **no engine
configuration removes the interference.**

## 7. Pre-registered expectations (so the result cannot be read after the fact)

1. The flag will be live in the launched server's own argv, and the H100's driver SIGINTs the cell
   otherwise. If the flag is not in argv, the cell is void, not a null.
2. Direction expected: monitor (alert) first-token times fall, cold robot recall first-token times
   rise. If monitor first-token times do NOT fall, the engine-side explanation for C5's trip is
   weakened, which is a result about the mechanism and not about the policy.
3. Both engine-flag cells (`covex-v6-state-uo` and `covex-v6-base`, seed 5) carry the SAME server,
   so the arm-to-arm comparison inside the flag condition is fair; neither may be compared with any
   committed cell of the same arm, because the server differs.
4. A changed C5 cap-floor occupancy under the flag is an EFFECT OF THE ENGINE, not of the policy.
   The policy code is byte-identical in these cells.

## 8. What would make the diagnostic uninterpretable (Step 0)

- the flag absent from argv (driver SIGINTs; void);
- a resolved `max_num_batched_tokens` other than 8192 (N must be re-derived, section 3);
- comparing a flag cell against a committed no-flag cell of the same arm, which is comparing two
  servers;
- quoting any number from these cells as a headline. They exist to attribute a mechanism.
