# StudyENG1e-chain: chained piece rebuilds under load, per engine step

Status: IN PROGRESS. Pre-registered in research/EXPERIMENTS.md (StudyENG1e-chain) before any run; HOLDOUT split
written 2026-11-17 14:31 before any run.

## Summary

(written after the sweep and the consistency check)

## 1. Design

Question: how do CHAINED piece rebuilds of a cold history interact with other requests under load, at the level of
which requests the engine serves in each step? StudyT0b and StudyPOL5 localized the cost model's remaining error to
chained rebuilds (arrivals during a chain over-predicted 1.6 to 1.8x), while single actions are predicted well
(StudyENG1d). Hypotheses (not exclusive): H-gap (between pieces the next piece is not yet schedulable and the engine
serves queued background requests in that gap), H-merge (background work shares a piece's step more than a single
action's), H-other.

Stack: StudyENG1c KV-HOST exactly: Qwen3-VL-32B-Instruct @0cfaf481, vLLM 0.31.0, StudySLICE1 E0 flags (8,192-token
budget, chunked prefill, async scheduling), native offloading connector with --kv-offloading-size 38,
--enable-logging-iteration-details, the fixed ENG1 stat-logger plugin, prefix caching ON, 128 GiB processor cache. The
flag list is diffed against ENG1c's DE_c38 server at every start and must be empty. The only addition is the
observe-only add-on (section 1.1), which needs no flag. GPU 2 of h100nvl, exclusive.

Caching state (stated explicitly, CLAUDE.md): prefix caching ON; the 38 GiB host tier is filled to 1.5x its capacity
with fresh histories at every server start, so every measured run sees a full host (steady state); every background
image and every action history carries a per-run uuid namespace, so background requests and the action's KV are cold
(first piece and mono: cached <= 16 tokens, checked per run). Mode B additionally puts the history's IMAGES (not its
KV) in the processor cache during setup and then flushes the vision-encoder cache (checked per piece); in mode A
nothing of the history is cached anywhere. With and without arms of a pair see the same cache state (0 cached-token
mismatches required).

Actions on a cold 11k-class history (the D2 ~11k sessions, 120 frames or slightly more): mono (one request with the
question, ESC_MAX_TOKENS); chain2048 (23 frames per piece); chain1024 (11 frames per piece). Pieces are prefix-chained
(piece j carries frames[:cut_j], so only its new frames are computed), max_tokens 1 except the last (question,
ESC_MAX_TOKENS), each released when the previous one completes: ENG1c Part D d_job exactly. ENG1c's cut rule
(range(n, frames, n) + [frames]) gives 6 pieces (chain2048) and 11 pieces (chain1024) on a 120-frame session and one
more, short, last piece on sessions with a few more frames (12 pieces seen in the smoke); the rule is kept unchanged.

Injection modes (user decision 8; reported separately, never pooled; B run first):
- B, ENG1c-exact. Per-run setup, identical in every arm: (i) the history once with image bytes under the SAME image
  uuids but a DIFFERENT header text (the images enter the processor cache; the history's own KV prefix stays cold
  because its first block differs), (ii) an encoder-cache flush: 200 fresh frames (about 18k encoder tokens) above the
  engine's 16,384-token encoder-cache budget (read from the server log at every start). Mono and pieces then carry
  uuid references only, as ENG1c's cold job did (ENG1c measured front end 14 to 20 ms).
- A, bytes. Fresh namespace, no setup; each piece sends its new frames as bytes, mono sends all 120 (as ENG1d's
  mono11k and single pieces).

Loads P25, P40, S2, S4 (StudyENG1 definitions and generator, seeds + 1,000,000); 20 paired with / without trials per
(mode, load, action), with / without order from the split file, 0 cached-token mismatches required, an independent
repeat of the without run on the first 3 FIT trials of each cell. HOLDOUT: 5 of 20 per (load, action), the SAME
trials in both modes (so a trace is never FIT in one mode and HOLDOUT in the other); recorded, not analysed. The
background trace of a (load, action, trial) is identical in the two modes.

Overhead gate (before any loaded run): servers in ABBA order (OFF, ON, ON, OFF), 5 discarded warm-up traces per server,
10 unloaded traces (mono, chain2048, chain1024 solo, mode B) + 10 P40 traces (chain1024 injected, mode B), split 5 / 5
over the two instances of each condition; gate-only seeds. Pass: ON / OFF ratio of the median step time (ENG1 plugin
elapsed_ms, the only step time an OFF server records) and of the median TTFT within plus or minus 1 % (95 % paired
bootstrap CIs over traces reported); membership sums equal the plugin rows on 100 % of joined steps;
instance-to-instance variation (unloaded traces, OFF2 / OFF1 and ON2 / ON1, median step time and median TTFT per
prompt token) within 1 %, else stop and report.

Mono cross-check (stop and report on failure, not void): median FIT TTFT sum within p10 x 0.75 to p90 x 1.25 of: mode
B, ENG1c Part D 38 GiB cold mono FIT (P25 3.65 to 22.71 s from 10 pairs, S2 8.52 to 16.61 s from 11 pairs; P40 and S4
have no gated reference for B; ENG1d reported ungated); mode A, ENG1d mono11k FIT (P25 4.69 to 37.62, P40 24.09 to
89.49, S2 14.26 to 27.84, S4 47.88 to 95.56 s).

### 1.1 Per-step membership add-on and its schema

`experiments/cost/eng1e_steplog/` is a `vllm.general_plugins` entry point loaded through PYTHONPATH (like the ENG1
plugin), active only when ENG1E_STEPLOG_PATH is set. It never touches the scheduler. In the engine-core process it
wraps three functions, each calling the original and returning its result unchanged, and only reads and copies:
`vllm.v1.engine.core.compute_iteration_details(scheduler_output)` (called once per non-empty step by
EngineCore.capture_iteration_details; the per-request scheduled tokens are copied with the same prefill / decode test
vLLM uses), `EngineCore._attach_iteration_details` (iteration index and elapsed_ms), and the executor's
`execute_model` (call and return wall time). Rows go through a queue to a background thread that writes plain jsonl
once per second; the runner gzips the file after the server stops.

File: `results/cost/study_eng1e/eng1e_steps_<server>.jsonl.gz`, one row per engine step that scheduled at least one
token (plus one `init` row):

| field | meaning |
|---|---|
| i | iteration index; equals the ENG1 plugin row's it[0] (join key) |
| t0 | wall clock (time.time()) when the engine core began waiting for this step's output (start of elapsed_ms) |
| el | elapsed_ms, the same value as the ENG1 plugin's it[5] |
| t1 | wall clock after update_from_output (when the step's outputs were processed) |
| ts | wall clock of the executor's execute_model call for this step (its dispatch, right after schedule()) |
| tr | wall clock when that call returned |
| r | list of [engine request id, scheduled tokens, "p" or "d", computed tokens before the step, encoder inputs] |

The engine request id is "chatcmpl-" + the client request id + "-" + 8 random hex characters. "p" = context phase
(new request, or cached request with 0 output tokens), "d" = decode; sum of "p" tokens = it[2], their count = it[1],
sum of "d" tokens = it[4], their count = it[3]. Step timing for consumers: end = t0 + el (output ready); start =
max(ts, end of the previous step); with async scheduling execute_model can block on the CPU side (multimodal input
preparation and the vision encoder) before the timed wait begins, so el alone understates such steps (smoke v1: a
mono first step of 8,192 tokens and 91 images showed el 0.025 ms after a 1.64 s execute_model call).

### 1.2 Implementation notes (fixes applied and reported, no design change)

- Encoder flush sized to the measured 16,384-token encoder budget (the pre-flight said 9k before the budget was read):
  200 fresh frames, at least 17,500 tokens checked per run, and the server start stops if the budget is not below it.
- Smoke v1 (14:32 to 14:43) passed every check but showed that elapsed_ms does not bound a step whose execute_model
  call blocks; the add-on gained the ts / tr fields and the analysis times steps as above. Smoke v1 files are kept as
  `eng1e_smokev1_*`; smoke v2 re-validates the add-on.
- 14:44: another user's job occupied GPU 2 after smoke v1; the runner refused to start (not exclusive) and a watcher
  waited for GPU 2 to be free for 120 s before smoke v2 (user instruction).

## 2. Smoke and mechanism verification (written before the sweep)

**Step 1, causal chain.** FORMULATION.md section Constraints (serving feasibility) and section Objective make the
latency of every request the binding term, and the policy's rollout (tested by StudyT0 / T0b) charges an action the
delay it imposes on other requests. A cold history can be rebuilt in one request (mono) or as a chain of
prefix-chained pieces. The chain tested here: each piece occupies the engine's token budget for its own prefill steps;
between pieces the next piece is not yet in the engine (the client has to see piece k complete and post piece k+1,
which then passes the API front end and waits for dispatch), so the engine is free to schedule whatever is queued
(H-gap); a background request arriving during the chain therefore waits only for the rest of the CURRENT piece, not
for the rest of the chain; alternatively or additionally the scheduler fills a piece's step with queued background
work because a 1,024 or 2,048-token piece leaves most of the 8,192-token budget unused (H-merge). Either way the delay
imposed by a chain is smaller than a contiguous occupancy of the same tokens would impose, which is the direction of
T0b's 1.6 to 1.8x over-prediction. The quantities that decide it are, per step, which requests were scheduled and
when the step ran: exactly what the add-on records.

**Step 5, alternative explanations.** (a) The chain imposes less simply because it is spread over a longer span at
lower intensity (fewer arrivals queue behind any single piece) without any gap service: distinguished by WHERE
during-chain arrivals are first scheduled (gap step vs piece step vs after the chain) and by rho_b against the piece
end vs the chain end. (b) The chain's cost is concentrated in its first piece (the full-history front end or
setup-like effects) rather than in the chain structure: distinguished by the imposed delay by bin (pre_fe vs piece vs
gap). (c) Mode effects: the bytes front end of mode A lengthens every gap (about 0.05 to 0.12 s of API time per
piece) and would favour H-gap for a reason absent from ENG1c's chains; the two modes are reported separately for this
reason. (d) CPU-side step blocking (execute_model holding the engine loop during multimodal preparation, found in
smoke v1) delays everything queued regardless of chain structure: visible as long dispatch-to-ready spans with no
other request scheduled, reported per action.

Smoke v2 (SMK_ON, 14:53 to 15:04; add-on with dispatch timestamps): flags identical to DE_c38; host fill 242,9xx
tokens (1.56x cap); one ON gate trace; one FIT pair per action and mode at P40 plus a repeat. 0 cached-token
mismatches over 3 x 2 pairs (50 to 62 compared background requests each); first piece / mono cached 0 tokens; every
piece's encoder inputs equal its new frames (setup flush effective); membership sums equal the plugin rows on 2,493 of
2,493 steps, all with dispatch timestamps. Setup (mode B) is the same two requests in every arm: history 2.6 to 2.8 s,
flush 4.6 to 5.2 s (client latency; the spread is run-to-run, not content).

**Step 2, instantiate each link (smoke v2, P40, one pair per cell).**

| causal link | implementing quantity | value in the smoke | varies as expected? | evidence |
|---|---|---|---|---|
| a piece occupies the budget for its own steps | piece prefill tokens and steps (add-on) | chain1024: 12 pieces of 995 to 1,031 tokens (last 249), 1 step each, about 0.16 s; chain2048: 6 pieces, 1 step each; mono: 2 steps (8,192 + rest) | yes, by action | step rows |
| between pieces the next piece is not schedulable | gap duration; next piece's submit-to-first-step | gap median 0.12 s (B chain1024), 0.21 s (B chain2048), 0.15 / 0.18 s (A); client turnaround 6 to 10 ms; API front end under 10 ms (B) vs 50 to 120 ms (A) | yes, by mode and piece size | step rows, frontend log |
| queued background work is served in the gap | gaps serving >= 1 background request; tokens | 100 % of gaps (B), 82 to 100 % (A); median 1 to 4 requests, 378 to 756 prefill tokens per gap | yes, present in every chain cell | step rows |
| arrivals wait for the current piece, not the chain | first service of during-chain arrivals; rho_b chain vs piece | B chain1024: 16 of 17 first served in a gap, rho_b chain 0.09, rho_b piece 1.03; B chain2048: 14 of 17, 0.29 / 1.87; mono: rho_b 0.93 to 2.08 | yes: chains low, mono about 1 or above | per-request rows |
| background work merged into piece steps (H-merge) | other-token share in piece steps | median 0.001 to 0.002 (only 1-token decodes; no other prefill in any piece step); mono 0.0 (B) / 0.17 (A) | present but tiny | step rows |
| imposed delay | sum of with - without latency (TTFT) | B: mono 27.7 (26.2), chain2048 13.1 (8.4), chain1024 4.9 (3.0) s; A: 35.5 (32.4), 2.9 (2.7), 4.1 (3.1) s | yes, by action | pairs |
| noise | repeat - without latency sum | -0.52 to +0.33 s | below every effect | repeats |

No link is ABSENT or CONSTANT. H-merge's quantity is present but near zero in the smoke; the sweep measures it.

**Step 3, one traced unit (mode B, P40, chain1024, trial 0, with-arm; times from the job start, engine clock).**
Piece 0: submitted 0.000, first step 0.142 to 0.304 (1,031 tokens, 11 images, 3 background decodes of 1 token), front
end 0.142 s, cached 0. Gap 0 (0.304 to 0.455): two steps, each one background prefill of 378 tokens (bg17, then bg18)
plus a decode. Piece 1: submitted 0.309 (client turnaround 5 ms), first step 0.455 to 0.616, 997 new tokens, 1,024
cached (the prefix chain works), 11 images. The pattern repeats; piece 11 (249 tokens, 1 image) ends at 3.765 s; chain
span 3.62 s, of which 59 % is piece steps. Background request 21 arrives at 0.964 (gap 2): first scheduled at 1.205
(end of piece 3, i.e. it waited out piece 3), TTFT 0.319 s with vs 0.131 s without, delta 0.188 s, rho_b against the
chain end 0.07. Of 17 during-chain arrivals, 16 were first served in a gap step and 1 in a piece step; trial totals:
latency 4.86 s, TTFT 3.03 s (piece bin 2.58 s, gap bin 2.11 s, pre_fe 0.22 s). Machine: other GPUs active (flagged, as
in ENG1d), host CPU mean 30 %.

**Step 4, negative control.** Removing the action (the without-arm repeat) gives the null: repeat - without latency
sums -0.52 to +0.33 s against 2.9 to 35.5 s with the action. The chain-structure control is mono on the same history,
trace and mode: the same tokens in one request give rho_b about 1 and 6 to 12x the imposed delay, so the gap
mechanism disappears when the chain does.

## 3. Overhead gate (first gate failed; corrected re-gate)

First gate (15:22 to 15:57; ABBA G_OFF1, G_ON1, G_ON2, G_OFF2; traces 0 to 4 on the first instance of each
condition, 5 to 9 on the second): FAIL under the pre-registered rule. Step time ON / OFF 0.9974 [0.977, 1.008]
unloaded and 0.9945 [0.988, 0.998] at P40 (within 1 %); TTFT 1.0064 [0.974, 1.028] unloaded and 1.0290 [0.989, 1.058]
at P40 (outside 1 %, CI includes 1); same-condition instance variation (unloaded, OFF2 / OFF1 and ON2 / ON1) up to
3.5 % on TTFT per prompt token and 1.7 % on step time, i.e. larger than the ON / OFF differences; but the two
instances ran different traces, so that variation also contained trace differences. Membership: 1,341 / 1,341 and
1,295 / 1,295 joined steps equal; the last 2 and 11 plugin steps of the two ON servers had no add-on row (the
writer's 1 s flush was cut by the shutdown). Run stopped and reported.

Correction (user ruling 2026-11-17, fixed before any re-gate data, disclosed here as the correction of an
under-powered gate: the original plus or minus 1 % TTFT tolerance was set without knowing the same-condition instance
variation): ABBA again (G2_OFF1, G2_ON1, G2_ON2, G2_OFF2), every server runs 5 discarded warm-ups and then ALL 10
unloaded and ALL 10 P40 gate traces (identical trace set on every instance); the add-on flushes after 0.5 s idle and at
exit, and the runner idles 2 s before stopping each server. Pass rule, both parts: (a) step time ON / OFF within plus
or minus 1 % at both loads (unchanged); (b) TTFT: the ON / OFF ratio's 95 % CI includes 1.0 AND its point estimate
deviates from 1.0 by no more than the larger of 1 % and the same-condition instance variation measured on the
identical traces (OFF1 vs OFF2 and ON1 vs ON2, both reported); membership sums equal the plugin rows on 100 % of joined
steps (joined-step counts reported).

Note on what the gate guards: every ENG1e with / without pair runs both arms on the same server with the add-on, so a
constant add-on overhead cancels in the imposed delay; the gate guards against an add-on that changes interaction
dynamics (which requests share a step, how long steps take), not against a constant offset.

Re-gate result (16:18 to 17:10; G2_OFF1, G2_ON1, G2_ON2, G2_OFF2; identical traces on every server): **FAILED under
the pre-registered (corrected) rule on the UNLOADED condition; PASSED at P40 on both parts; membership exact.** The
gate is not restated as passed anywhere in this report.

| condition | quantity | ON / OFF | 95 % CI | instance OFF2 / OFF1, ON2 / ON1 | tolerance | result |
|---|---|---|---|---|---|---|
| unloaded | median step time | 0.9900 | 0.984 to 1.003 | 0.986 (OFF1 147.2 vs OFF2 145.2 ms), 0.997 | 1 % | FAIL (outside plus or minus 1 %; ON faster) |
| unloaded | median TTFT | 1.0159 | 1.006 to 1.023 | 1.001, 0.994 | 1 % | FAIL (CI excludes 1) |
| P40 | median step time | 0.9953 | 0.991 to 1.000 | 1.001, 1.001 | 1 % | PASS |
| P40 | median TTFT | 0.9960 | 0.989 to 1.019 | 1.012, 1.037 | 3.7 % | PASS |
| membership | add-on vs plugin rows | 2,075 / 2,075 (G2_ON1), 2,071 / 2,071 (G2_ON2) joined steps equal; 0 plugin steps without an add-on row | | | | PASS |

Unloaded TTFT by request class (median over 10 traces x 2 instances per condition, mode B, solo):

| request class | n per condition | ON median (s) | OFF median (s) | ON / OFF |
|---|---|---|---|---|
| mono | 20 | 2.1698 | 2.1635 | 1.003 |
| chain2048 first piece | 20 | 0.3702 | 0.3699 | 1.001 |
| chain2048 middle pieces | 80 | 0.4420 | 0.4409 | 1.003 |
| chain2048 last piece | 20 | 0.2261 | 0.2265 | 0.999 |
| chain1024 first piece (after a 1 s idle) | 20 | 0.2114 | 0.2010 | 1.052 |
| chain1024 middle pieces | 190 | 0.2410 | 0.2394 | 1.007 |
| chain1024 last piece | 20 | 0.2356 | 0.2971 | 0.793 (two clusters: 1-frame vs 10-frame last pieces) |

Reading: the unloaded step-time failure is in the direction an add-on cannot cause (ON faster) and smaller than the
same-condition OFF1 / OFF2 difference on identical traces (1.4 %); the pooled unloaded TTFT median mixes request
classes with very different TTFTs; per class the ratios are within 0.7 % except the chain1024 first piece (+5.2 %,
about 10 ms; per trace OFF1 0.188 to 0.210 s, OFF2 0.190 to 0.217 s, ON 0.192 to 0.223 s), which is the only
consistent-looking shift and cannot be separated from instance noise with these data. A plausible mechanism, if it is
real: the add-on's writer thread flushes after 0.5 s idle and contends for the engine core's GIL when a request
arrives after an idle period.

User ruling (2026-11-17, option 1 with conditions): run the sweep with the add-on UNCHANGED; every output of the sweep
is labelled "add-on failed unloaded overhead gate; passed at P40" (field `addon_gate` on every request and fill row,
and in the run meta); the analysis flags any unloaded cell or request that starts after an engine idle period and
reports the chain1024 first-piece-after-idle TTFT separately from the other classes. All sweep cells are loaded; each
with / without pair runs both arms with the add-on, so a constant offset cancels in the imposed delay.

Proposed fix, NOT implemented in ENG1e (for StudyENG1f, with its own gate fixed in advance including an instance-noise
allowance on step time): the add-on writer never flushes on idle; it writes every 2 s while steps arrive and once at
exit (atexit), and the runner idles 2.5 s before stopping a server so the last rows land.
