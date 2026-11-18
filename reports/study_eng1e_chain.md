# StudyENG1e-chain: chained piece rebuilds under load, per engine step

Status: COMPLETE 2026-11-17 (h100nvl GPU 2). Pre-registered in research/EXPERIMENTS.md (StudyENG1e-chain) before any
run; HOLDOUT split written 2026-11-17 14:31 before any run. Every sweep output carries the label **"add-on failed
unloaded overhead gate; passed at P40"** (section 3; user ruling, option 1).

## Summary

**H-gap SUPPORTED in all 16 chain cells (both modes, all four loads); H-merge PARTIAL in 11, REJECTED in 4, SUPPORTED
in 1 (mode A, S4, chain2048).** The engine runs every piece of a chained rebuild in exactly ONE step (1,024-token
pieces about 0.19 s, 2,048-token pieces about 0.36 to 0.47 s), and between pieces there is a gap of 0.11 to 0.40 s
in which the next piece is not yet scheduled (the client turnaround is 7 to 14 ms; the rest is the next piece waiting
for dispatch behind the steps the engine runs meanwhile). The engine serves queued background requests in 77 to
100 % of those gaps, and 65 to 90 % of the background requests that arrive during a chain are first scheduled in a
gap step. So an arrival waits for the CURRENT piece, not for the chain: rho_b against the chain end is 0.06 to 0.26,
against the current piece's end 0.69 to 2.12. That is why a chain imposes 8 to 52 % of the delay a mono rebuild of the
same history imposes (latency sums: chains 2.1 to 27.0 s, mono 14.1 to 87.9 s), and it is the mechanism of the
over-prediction T0b and POL5 localized to chained rebuilds. Background prefill DOES share piece steps (13 to 29 % of
piece steps at P25, P40 and S2, 43 to 79 % at S4; up to 5 prefills in one piece step), but in most cells the median
piece step carries no other prefill, so the pre-registered H-merge test (median other-token share vs mono) is met only
at S4. Every piece ran in one step, not the about 1.8 StudyPOL6 derived by subtraction from ENG1c. Modes differ in
the per-gap front end (API submit to engine-added: mode B 14 to 16 ms, as ENG1c; mode A 72 to 112 ms, as ENG1d), which
lengthens mode A's gaps by about 0.05 to 0.07 s but does not change any verdict. Gates: all six gated mono
cross-checks PASS; 0 cached-token mismatches over 26,088 compared background requests; every piece's encoder check
passed; the per-step add-on's overhead gate FAILED on the unloaded condition and PASSED at P40 (section 3).

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

## 4. Run record

Sweep 2026-11-17 17:17:49 to 22:05:20 (4.8 h), eight servers (B_P40, B_S4, B_P25, B_S2, A_P40, A_S4, A_P25, A_S2),
each with flags identical to ENG1c DE_c38, the add-on installed, mmap 40.8 GB (38 GiB), encoder budget 16,384, host
filled to 1.56x cap before measuring. Not VOID; no monitor exemption events; nothing unfinished (the 6 h guard, counted
from the sweep start, was not reached). 24 cells x 20 pairs: 15 FIT + 5 HOLDOUT per cell, 3 repeats per cell. Pair
check: 0 cached-token mismatches over 26,088 compared background requests. Every with-run's first piece (and mono) had
0 cached tokens; every piece's encoder inputs covered its new frames (0 failures), so mode B's encoder-cache flush
worked in every run. Mono cross-checks (median FIT TTFT sum): B P25 15.13 s (band 3.65 to 22.71, PASS), B S2 12.80 s
(8.52 to 16.61, PASS), A P40 35.75 s (24.09 to 89.49, PASS), A S4 72.80 s (47.88 to 95.56, PASS), A P25 24.60 s
(4.69 to 37.62, PASS), A S2 21.22 s (14.26 to 27.84, PASS). B at P40 and S4 has no gated reference; against ENG1d's
widened band (reported, ungated) B P40 21.70 s and B S4 45.46 s fall just below it, as does B S2 12.80 s, which is
the expected direction: mode B has no 0.57 s bytes front end in front of mono (section 7).

Machine: every trial is flagged on the GPU criterion (GPUs 0, 1 and 3 belong to other users and were busy all
evening, as in ENG1d), so the "unflagged" tables are empty; host CPU trial means at most 15.1 %, so no trial is
flagged on CPU and the "CPU ok" tables equal the main tables. GPU 2 was exclusive throughout (exclusivity monitor
clean).

## 5. Verdicts per mode, load and action (FIT, 15 trials per cell)

Decision rules as pre-registered (section 1). "first gap / piece" = share of during-chain arrivals first scheduled in a
gap step / in a piece step; rho_b chain = delta / (chain end - arrival), median with trial-cluster 95 % CI; "share
diff" = median other-token share of piece steps minus mono's, with trial-cluster bootstrap CI.

| mode | load | action | gaps serving | first gap | first piece | rho_b chain [CI] | share diff [CI] | H-gap | H-merge |
|---|---|---|---|---|---|---|---|---|---|
| B | P25 | chain1024 | 0.82 | 0.85 | 0.12 | 0.080 [0.073, 0.087] | 0.001 [-0.022, 0.001] | SUPPORTED | PARTIAL |
| B | P25 | chain2048 | 0.93 | 0.90 | 0.08 | 0.197 [0.173, 0.224] | 0.001 [0.000, 0.001] | SUPPORTED | REJECTED |
| B | P40 | chain1024 | 0.88 | 0.81 | 0.14 | 0.092 [0.079, 0.115] | 0.002 [-0.022, 0.002] | SUPPORTED | PARTIAL |
| B | P40 | chain2048 | 1.00 | 0.80 | 0.09 | 0.237 [0.210, 0.273] | 0.002 [0.001, 0.002] | SUPPORTED | REJECTED |
| B | S2 | chain1024 | 0.99 | 0.85 | 0.11 | 0.079 [0.072, 0.086] | 0.001 [0.001, 0.001] | SUPPORTED | PARTIAL |
| B | S2 | chain2048 | 1.00 | 0.85 | 0.09 | 0.208 [0.194, 0.218] | 0.001 [0.001, 0.001] | SUPPORTED | REJECTED |
| B | S4 | chain1024 | 1.00 | 0.82 | 0.14 | 0.102 [0.097, 0.105] | -0.042 [-0.070, 0.218] | SUPPORTED | PARTIAL |
| B | S4 | chain2048 | 1.00 | 0.77 | 0.14 | 0.264 [0.254, 0.273] | 0.109 [0.081, 0.109] | SUPPORTED | PARTIAL |
| A | P25 | chain1024 | 0.77 | 0.82 | 0.15 | 0.058 [0.053, 0.067] | -0.053 [-0.105, -0.053] | SUPPORTED | PARTIAL |
| A | P25 | chain2048 | 0.91 | 0.83 | 0.13 | 0.153 [0.140, 0.175] | -0.053 [-0.105, -0.053] | SUPPORTED | PARTIAL |
| A | P40 | chain1024 | 0.85 | 0.76 | 0.22 | 0.078 [0.070, 0.090] | 0.001 [-0.162, 0.002] | SUPPORTED | PARTIAL |
| A | P40 | chain2048 | 1.00 | 0.72 | 0.21 | 0.194 [0.177, 0.225] | 0.005 [-0.157, 0.154] | SUPPORTED | PARTIAL |
| A | S2 | chain1024 | 0.94 | 0.86 | 0.10 | 0.056 [0.052, 0.061] | -0.104 [-0.132, -0.104] | SUPPORTED | REJECTED |
| A | S2 | chain2048 | 1.00 | 0.83 | 0.11 | 0.170 [0.157, 0.174] | -0.104 [-0.133, -0.104] | SUPPORTED | PARTIAL |
| A | S4 | chain1024 | 1.00 | 0.72 | 0.25 | 0.080 [0.076, 0.090] | 0.115 [0.053, 0.115] | SUPPORTED | PARTIAL |
| A | S4 | chain2048 | 1.00 | 0.65 | 0.28 | 0.208 [0.201, 0.214] | 0.107 [0.046, 0.138] | SUPPORTED | SUPPORTED |

H-gap: every cell meets all three SUPPORTED conditions with a wide margin (gaps serving >= 0.77, first-in-gap >= 0.65,
rho_b chain <= 0.26). H-merge: the PARTIAL cells are those where some during-chain arrivals are first served in a
piece step (8 to 28 %) but the median piece step carries no other work beyond 1-token decodes; mono in mode A carries
some other prefill (its median share 0.05 to 0.16), which is why several mode A differences are negative. Rule 2
classification: H-merge's REJECTED cells are REAL NEGATIVES in the sense of the pre-registered test (the mechanism's
quantity, other work in piece steps, is measured directly on every step and is present, section 6), not
inconclusive.

H-other: nothing else is needed to explain the chain's lower cost. One further fact, recorded for the step model: with
async scheduling a step's execute_model call can block on the CPU side (multimodal preparation and the vision
encoder) before the engine's timed wait begins, so the ENG1 plugin's elapsed_ms understates image-heavy steps (mono's
first 8,192-token step: elapsed_ms near 0 after a 1.0 to 1.6 s dispatch). Any step model fitted on elapsed_ms alone
inherits this.

## 6. Step composition (measured per step by the add-on; StudyPOL6 section 11.4 targets)

| mode | load | action | steps per piece (median, max) | piece step duration ms (median [p10, p90]) | piece steps with other prefill | prefills per piece step (median, max) | encoder inputs per piece step (median) |
|---|---|---|---|---|---|---|---|
| B | P25 | chain1024 | 1, 1 | 194 [159, 231] | 0.13 | 1, 3 | 11 |
| B | P25 | chain2048 | 1, 1 | 364 [174, 415] | 0.16 | 1, 2 | 23 |
| B | P25 | mono | 2, 2 | 1,068 [552, 1,600] | 0.33 | 1, 3 | 62 |
| B | P40 | chain1024 | 1, 1 | 198 [159, 253] | 0.21 | 1, 3 | 11 |
| B | P40 | chain2048 | 1, 1 | 379 [186, 443] | 0.24 | 1, 5 | 23 |
| B | P40 | mono | 2, 2 | 1,193 [596, 1,592] | 0.33 | 1, 4 | 64 |
| B | S2 | chain1024 | 1, 1 | 192 [157, 224] | 0.13 | 1, 2 | 11 |
| B | S2 | chain2048 | 1, 1 | 358 [203, 417] | 0.17 | 1, 3 | 23 |
| B | S2 | mono | 2, 2 | 1,037 [578, 1,577] | 0.27 | 1, 3 | 63 |
| B | S4 | chain1024 | 1, 1 | 208 [159, 262] | 0.43 | 1, 3 | 11 |
| B | S4 | chain2048 | 1, 1 | 388 [236, 490] | 0.59 | 2, 5 | 23 |
| B | S4 | mono | 2, 2 | 1,374 [721, 1,482] | 0.70 | 2, 4 | 63 |
| A | P25 | chain1024 | 1, 1 | 192 [143, 230] | 0.17 | 1, 4 | 11 |
| A | P25 | chain2048 | 1, 1 | 366 [164, 444] | 0.22 | 1, 3 | 23 |
| A | P25 | mono | 2, 2 | 1,293 [650, 1,586] | 0.50 | 1.5, 7 | 65 |
| A | P40 | chain1024 | 1, 1 | 196 [154, 263] | 0.29 | 1, 5 | 11 |
| A | P40 | chain2048 | 1, 1 | 399 [230, 498] | 0.47 | 1, 5 | 23 |
| A | P40 | mono | 2, 2 | 1,486 [803, 1,609] | 0.47 | 1, 11 | 65 |
| A | S2 | chain1024 | 1, 1 | 183 [142, 222] | 0.12 | 1, 2 | 11 |
| A | S2 | chain2048 | 1, 1 | 360 [188, 427] | 0.23 | 1, 2 | 23 |
| A | S2 | mono | 2, 2 | 1,288 [722, 1,584] | 0.50 | 2, 5 | 64 |
| A | S4 | chain1024 | 1, 1 | 231 [164, 302] | 0.70 | 2, 3 | 12 |
| A | S4 | chain2048 | 1, 1 | 474 [230, 567] | 0.79 | 3, 5 | 25 |
| A | S4 | mono | 2, 2 | 1,590 [968, 1,631] | 0.50 | 3, 9 | 65.5 |

Step durations here use the dispatch-based start (section 1.1). The p10 of each piece-step duration is low because a
piece's step is sometimes dispatched while the previous step is still running (start = previous end). Reading against
StudyPOL6 section 11: (1) steps per piece is 1 in every cell, not about 1.8; (2) the engine does merge background
prefills into piece steps, less often than pol4 (13 to 29 % of piece steps at the ENG1c loads P25 / S2 in mode B
against pol4's 55 % and 69 %, and against the 40 % and 48 % POL6 derived by subtraction from ENG1c), with at most 3 to 5
prefills in one piece step (pol4: up to 6, 8 and 21); (3) encoder inputs per piece step equal the piece's new frames
(11 or 23) in both modes. Mode A merges more often than mode B in 7 of the 8 chain (load, piece size) pairs (the exception: S2 chain1024, 0.12 vs 0.13).

## 7. Imposed delay, its decomposition, and the noise ceiling

Total imposed delay per pair (FIT, sum over background requests of with minus without), median [p10, p90]; latency is
primary, TTFT secondary; noise = |repeat - without| latency sum, median over the cell's 3 repeats.

| mode | load | action | latency sum s | TTFT sum s | noise s | chain / mono (latency) | share by bin: pre_inj / pre_fe / piece / gap / post |
|---|---|---|---|---|---|---|---|
| B | P25 | chain1024 | 3.66 [1.71, 4.28] | 2.32 | 0.09 | 0.22 | 0.01 / 0.00 / 0.63 / 0.35 / 0.01 |
| B | P25 | chain2048 | 6.15 [3.47, 7.96] | 3.62 | 0.19 | 0.37 | 0.00 / 0.01 / 0.75 / 0.23 / 0.00 |
| B | P25 | mono | 16.46 [7.52, 23.36] | 15.13 | 0.02 | 1 | 0.05 / 0.08 / 0.83 / 0 / 0.04 |
| B | P40 | chain1024 | 5.39 [3.95, 9.26] | 4.02 | 0.03 | 0.22 | 0.02 / 0.03 / 0.55 / 0.40 / 0.01 |
| B | P40 | chain2048 | 12.59 [6.52, 15.92] | 8.39 | 0.09 | 0.52 | 0.04 / 0.02 / 0.59 / 0.32 / 0.04 |
| B | P40 | mono | 24.25 [13.35, 42.93] | 21.70 | 0.07 | 1 | 0.06 / 0.12 / 0.76 / 0 / 0.07 |
| B | S2 | chain1024 | 3.19 [2.81, 3.38] | 1.93 | 0.03 | 0.23 | 0.02 / 0.01 / 0.65 / 0.33 / 0.00 |
| B | S2 | chain2048 | 6.21 [5.65, 6.68] | 3.42 | 0.01 | 0.44 | 0.02 / 0.00 / 0.74 / 0.23 / 0.00 |
| B | S2 | mono | 14.13 [13.26, 15.54] | 12.80 | 0.13 | 1 | 0.03 / 0.07 / 0.86 / 0 / 0.04 |
| B | S4 | chain1024 | 14.54 [13.35, 14.93] | 9.94 | 0.08 | 0.26 | 0.01 / 0.01 / 0.51 / 0.46 / 0.01 |
| B | S4 | chain2048 | 27.00 [25.14, 28.49] | 18.48 | 0.13 | 0.49 | 0.01 / 0.02 / 0.49 / 0.45 / 0.02 |
| B | S4 | mono | 55.31 [52.09, 59.11] | 45.46 | 0.04 | 1 | 0.05 / 0.05 / 0.71 / 0 / 0.18 |
| A | P25 | chain1024 | 2.07 [1.65, 3.91] | 1.82 | 0.06 | 0.08 | 0.01 / 0.02 / 0.49 / 0.49 / -0.01 |
| A | P25 | chain2048 | 4.09 [2.03, 5.45] | 3.33 | 0.04 | 0.15 | 0.00 / 0.09 / 0.51 / 0.40 / 0.01 |
| A | P25 | mono | 27.10 [11.21, 34.72] | 24.60 | 0.02 | 1 | 0.00 / 0.40 / 0.58 / 0 / 0.02 |
| A | P40 | chain1024 | 5.42 [3.73, 7.68] | 4.31 | 0.09 | 0.14 | 0.02 / 0.03 / 0.38 / 0.51 / 0.05 |
| A | P40 | chain2048 | 9.59 [4.20, 14.36] | 7.71 | 0.19 | 0.24 | 0.01 / 0.05 / 0.47 / 0.45 / 0.02 |
| A | P40 | mono | 39.59 [23.21, 53.69] | 35.75 | 0.08 | 1 | 0.00 / 0.32 / 0.59 / 0 / 0.09 |
| A | S2 | chain1024 | 2.15 [1.98, 2.42] | 1.79 | 0.04 | 0.09 | 0.01 / 0.03 / 0.40 / 0.55 / 0.01 |
| A | S2 | chain2048 | 3.68 [3.35, 4.52] | 3.36 | 0.05 | 0.16 | 0.00 / 0.06 / 0.49 / 0.45 / 0.00 |
| A | S2 | mono | 23.35 [20.64, 24.86] | 21.22 | 0.03 | 1 | 0.00 / 0.35 / 0.62 / 0 / 0.03 |
| A | S4 | chain1024 | 11.08 [9.53, 12.48] | 9.65 | 0.04 | 0.13 | 0.00 / 0.02 / 0.44 / 0.53 / 0.01 |
| A | S4 | chain2048 | 21.56 [18.67, 22.64] | 17.81 | 0.17 | 0.25 | 0.00 / 0.04 / 0.46 / 0.49 / 0.02 |
| A | S4 | mono | 87.89 [77.10, 92.74] | 72.80 | 0.06 | 1 | 0.00 / 0.22 / 0.63 / 0 / 0.16 |

Noise ceiling: the median repeat noise (0.01 to 0.19 s) is 1 to 3 % of the smallest chain effect and far below every
mono effect; every cell's effect is outside its noise. The gap bin carries 23 to 55 % of a chain's imposed delay: those
are requests that arrive between pieces and still wait (for the steps already queued ahead of them and for the next
piece once it is dispatched before them), so the gap reduces, but does not remove, the delay of arrivals near it.

Per-gap front end, per mode (FIT with-runs, all pieces after the first; API = client submit to the engine's "Added"
log line; the rest of a gap is the wait for dispatch):

| mode | action | API front end median [p90] | gap duration median by load (P25 / P40 / S2 / S4) | client turnaround |
|---|---|---|---|---|
| B | chain1024 | 14.2 ms [20.2] | 0.107 / 0.122 / 0.111 / 0.224 s | 7 to 10 ms |
| B | chain2048 | 16.0 ms [20.6] | 0.179 / 0.238 / 0.186 / 0.394 s | 9 to 11 ms |
| A | chain1024 | 71.7 ms [83.4] | 0.154 / 0.173 / 0.164 / 0.252 s | 9 to 11 ms |
| A | chain2048 | 111.8 ms [132.0] | 0.205 / 0.249 / 0.212 / 0.398 s | 11 to 14 ms |

Mono's API front end is 20.3 ms in mode B and 567.9 ms in mode A (the 22.7 MB body), which is why mode A's mono puts
22 to 40 % of its imposed delay in the pre_fe bin against 5 to 12 % in mode B, and why mode B's mono sits below ENG1d's
band (section 4).

Chain1024 first piece, reported separately (user ruling): its TTFT median by cell is 0.21 to 0.31 s against 0.29 to
0.50 s for the later pieces; in the loaded sweep no chain's first piece started after an engine idle period of 0.5 s or
more; one mono request in each of A P40 and B P40 did (the overhead-gate concern of section 3 applies to such starts).

## 8. Results consistency check (six checks)

1. **Cross-check against committed measurements.**

| quantity | this run | prior run | source | ratio | agree |
|---|---|---|---|---|---|
| mono TTFT sum, B P25 / S2 (ENG1c-exact) | 15.13 / 12.80 s | 13.31 / 12.80 s | ENG1c Part D 38 GiB cold mono FIT | 1.14 / 1.00 | yes |
| chain latency sum, B P25 chain2048 / chain1024 | 6.15 / 3.66 s | 5.87 / 2.89 s | ENG1c Part D 38 GiB cold piece2048 / piece1024 FIT | 1.05 / 1.27 | yes |
| chain latency sum, B S2 chain2048 / chain1024 | 6.21 / 3.19 s | 5.41 / 3.11 s | same | 1.15 / 1.03 | yes |
| mono TTFT sum, A P25 / P40 / S2 / S4 | 24.60 / 35.75 / 21.22 / 72.80 s | 16.69 / 44.87 / 20.90 / 69.87 s | ENG1d mono11k FIT | 1.47 / 0.80 / 1.02 / 1.04 | yes (within 2x) |
| API front end, uuid-reference piece | 14 to 16 ms | 14 to 15 ms | ENG1c Part D frontend log | 1.0 | yes |
| API front end, bytes piece1024 / piece2048 / mono | 72 / 112 / 568 ms | 79 / 140 / 555 ms | ENG1d frontend log | 0.91 / 0.80 / 1.02 | yes |
| rho_b, mono (arrivals during the action) | 0.93 to 0.95 | about 1.0 (H1), 1.17 to 1.43 at 25 to 75 % | ENG1d | under 2x | yes (definition differs: here against the end of the whole mono, including arrivals in its first step) |

No disagreement over 2x.

2. **Physical plausibility.** A 1,024-token piece in one step of about 0.19 s is about 5,300 tokens/s including 11
images; a 2,048-token piece in 0.36 s about 5,700 tokens/s; mono's 11k tokens in two steps (1.0 to 1.6 s for the
first 8,192-token step with 62 to 65 images) is consistent with ENG1's 2.74 s cold TTFT. None is faster than the
committed H100 prefill curves.

3. **Distribution sanity.** Every table reports p10 and p90 or a CI; no quantity is constant across conditions where
inputs vary (chain spans 2.9 to 5.3 s, gap durations rise with load, piece step durations differ by piece size).

4. **Definition audit.** Pieces: ENG1c's cut rule unchanged (6 or 7 pieces of 23 frames, 11 or 12 of 11 frames,
depending on the session's frame count). Mono: ENG1d's mono11k in mode A, ENG1c's cold mono in mode B. Imposed
delay: ENG1c's latency sum (primary) and ENG1d's TTFT sum (secondary). rho_b: ENG1d's definition with the action's end
taken as the chain end (last piece's last prefill step end); rho_b piece uses the current piece's end. Bins as
pre-registered; gap k includes piece k+1's front-end window. Step times use the dispatch-based start (section 1.1),
which differs from ENG1's elapsed_ms-only step time for image-heavy steps (section 5, H-other).

5. **Claim linkage.** FORMULATION.md section Constraints (serving feasibility): a cold history's rebuild cost to
OTHER devices depends on how it is released, and chaining moves most of it off the other devices: supports the
policy's adaptive-granularity mechanism (spec v4 section 8.4) and explains the T0b over-prediction on chains. It does
not speak to quality or to representation choice.

6. **Proxy validity.** Arrival = client submit time (as ENG1d); "first served" = the request's first scheduled step in
the add-on's log (direct, not a proxy); gap boundaries from engine step times (dispatch-based start, output-ready
end). The step log was written by an add-on that FAILED the unloaded overhead gate (section 3); every sweep cell is
loaded and both arms of every pair ran with the add-on, so the imposed delays are unaffected by a constant add-on
offset; the per-step timings could carry a dynamic effect only of the size bounded at P40 (step time 0.9953 [0.991,
1.000], TTFT 0.9960 [0.989, 1.019]).

All six checks PASS.

## 9. HOLDOUT

120 pairs (5 per cell x 24 cells) recorded in `eng1e_requests_h100nvl.jsonl.gz` with `holdout: true`, NOT analysed;
split in `eng1e_holdout_split.json` (written 14:31, before any run). The same trials are HOLDOUT in both modes.

## 10. Implications (separate from the findings)

- For the cost model (T0b, POL5, POL6 Part B): a chained rebuild should be charged as a sequence of one-step pieces with
  a real gap between them in which queued work runs; an arrival during the chain pays for the rest of the current
  piece plus the queue ahead of it, not for the rest of the chain. The in-step merge is real but bounded (median 1,
  at most 3 to 5 prefills per piece step) and much rarer than pol4's 55 to 69 %; fitting merge capacity and the
  one-step-per-piece structure on these FIT data is the direct next step for POL6 Part B.
- For the policy (spec v4 section 8.4): chaining keeps 48 to 92 % of a cold rebuild's delay off other devices at
  every load tested, in both injection modes, so the adaptive-granularity mechanism has a large, measured lever; the
  gap per piece (0.11 to 0.40 s) is the price paid by the job itself (chain spans 2.9 to 5.3 s against 2.1 to 2.6 s
  for mono).
- For the step model: elapsed_ms understates image-heavy steps under async scheduling; the dispatch time is needed.
- For ENG1f: the add-on writer fix in section 3 (no idle flush) with its own gate.
- The ENG1c versus ENG1d puzzle of StudyPOL6 section 11.3 is answered for the merge question: both injection modes
  merge background prefill into piece steps at comparable, modest rates (mode A more often in 7 of 8 pairs), so the difference
  ENG1d saw (0 of 248 admitted) concerns single pieces, not chains.

## 11. Files

New: `experiments/cost/study_eng1e_chain.py`, `experiments/cost/study_eng1e_analyse.py`,
`experiments/cost/eng1e_steplog/` (add-on and dist-info), `reports/study_eng1e_chain.md`, `results/cost/study_eng1e/`
(split; smoke v1 / v2; both gates; sweep requests, frontend, machine, monitor and fill rows as `.jsonl.gz`; ENG1 plugin
rows per server in `eng1e_statlog/`; add-on step rows `eng1e_steps_<server>.jsonl.gz`; run meta; `eng1e_results.json`).
Changed: `research/EXPERIMENTS.md` (pre-registration row, verdict in place), `results/INDEX.md`, `research/STATUS.md`.
Note: `eng1e_gate_h100nvl.jsonl` (6.8 MB, both gates' rows) was committed and pushed before the overnight 5 MB rule;
it is left as committed (no history rewrite).
