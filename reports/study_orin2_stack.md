# StudyORIN2-stack: Jetson AGX Orin device-stack fidelity fixes (design log D61)

Machine: Jetson AGX Orin (the session that ran StudyORIN1-dense). Repo HEAD contained
f5413e5 at the start. Two device-stack fidelity fixes:

- Part 1: fit the Orin 4B's own score calibration (raw log P(Yes) to probability),
  because StudyORIN1-dense found Orin scores about 1 log unit from the H100 4B's, so
  the H100-fitted map (StudyCTRL1c) cannot be reused.
- Part 2: measure the device's warm recall latency on a path that does NOT re-send the
  whole image history on every call. StudyORIN1-dense Part 3 found server TTFT
  1.41 s (11k) / 3.43 s (28k) of which model work was only 0.13 to 0.19 s; the rest is
  the llama.cpp OpenAI-compatible API re-sending and re-parsing every history image. That
  path is an API artifact, not the device's real cost, and using it as the device
  baseline would flatter the cloud.

## Summary

- Part 1 COMPLETE. 6,010 StudyD3 DEV N=1 requests scored on the Orin (601 clips x 10
  event-anchored offsets), 0 null, 0 neither, clock pinned on every row. Orin vs H100 4B
  Pearson 0.9418 with a mean offset of -0.2576 log units (confirms the device needs its
  own map). One Platt map fit for the Orin 4B: a = 0.114932, b = 1.174287 (raw log P(Yes)
  at calibrated p = 0.5 is -10.2173). The fit routine reproduces StudyCTRL1c's published
  H100 4B map to < 1e-4 (validation). After calibration the Orin 4B sits -0.0171 log-odds
  from the calibrated 32B on D3 DEV, tighter than the H100 4B's -0.1197.
- Part 2 COMPLETE. No server-native path can append a question to a cached multimodal
  prefix without re-sending the image bytes (source investigation at c0fd786), so an
  in-process libllama + libmtmd harness was built. Equivalence gate passed (token-identical
  prompts, identical answers and top-20 token sets, first-token logprobs within 0.15 nats).
  The harness warm-recall TTFT p50 is 0.146 s (11k) and 0.225 s (28k) versus the server
  path's 1.416 s and 3.433 s: ratios 9.7x and 15.2x. The server TTFT is about 91% API
  image re-send (everything_else 1285 ms of 1416 ms at 11k; 3245 ms of 3433 ms at 28k),
  not device compute. The harness is the device warm-recall baseline for policy evaluation;
  the server path is an API artifact (D61).

## Stack (verified, identical to StudyORIN1-dense)

llama.cpp c0fd786 (binary /home/nesl/llama.cpp/build/bin/llama-server); Qwen3-VL-4B-Instruct
F16 GGUF (sha256 4a6fb1ed...ec761) + mmproj-F16 (sha256 256f3a43...985331); server flags
-ngl 99 -fa on -c 57344 --jinja --reasoning-format deepseek -np 1 (one slot, no continuous
batching); MAXN power mode 0; GPU clock pinned 1,300,500,000 Hz and logged per request;
greedy, seed 0; cache_prompt false (Part 1 cold scoring). One request at a time throughout.

## Part 1: Orin 4B score calibration on the StudyD3 DEV split

### Inputs and frames

The 6,010 StudyD3 DEV N=1 requests are the 601 DEV-split clips (sha256(video_id) lowest-30%
DEV, StudyB amendment 2) times 10 event-anchored offsets. Requests were rebuilt
byte-identically to the StudyD15 contract: header "The following is 1 dashcam frame.", one
small 768x432 PNG, the Nexar query; prompt_tokens 378 on every row (verified). The D3 DEV
frames were not on the Orin at the start (0 of 6,010 present); they were transferred by the
Mac to /home/nesl/data/d14_n1/<clip>/<key>.png and every frame was sha256-verified against
results/dashcam/study_d3_nexar/frames_sha256_manifest.jsonl.gz before scoring (gate:
checked 6,010 / 6,010, 0 missing, 0 mismatch, 601 clips). The 10,660 integer-second StudyD15
frames were never touched.

### Scoring

All 6,010 scored on the Orin with StudyD15's score_request unchanged (cache_prompt false,
cold prompt; first-token Yes/(Yes+No) top-20 mass; score = log P(Yes) floored at 1e-12),
one request at a time, resumable by request_id, at 1.89 req/s. Sanity: 0 null scores, 0
neither rows, clock pinned on all 6,010 rows.

### Gates and fit

| quantity | value |
|---|---|
| Orin vs H100 4B Pearson (n = 6,010) | 0.9418 |
| mean (Orin minus H100) log P(Yes) | -0.2576 |
| null scores / neither rows | 0 / 0 |
| clock pinned all rows | yes |

Orin vs H100 4B agreement (Pearson 0.9418) matches StudyORIN1-dense's independent H100
agreement of 0.9426 and confirms the preserved-ordering, offset-absolute-score finding: the
device cannot reuse the H100 map.

The Platt map (log_odds = a * log(p_yes) + b, clip-level label) was fit on the 601 DEV clips
(per-request feature, clip label) with sklearn LogisticRegression at its default settings
(C = 1.0, lbfgs). StudyCTRL1c's own ctrl1c_calibrate.py was absent from the repo at f5413e5
(not tracked, not in history), so the routine was identified empirically: refitting it on the
H100 4B D3 DEV scores reproduces StudyCTRL1c's published H100 4B map (a = 0.114603,
b = 1.140751) to a = 0.114596, b = 1.140683, errors 7e-6 and 6.8e-5 (both < 1e-4). A
hand-rolled unregularized Newton fit diverges because the H100 scores are near-separable;
the default L2 is what StudyCTRL1c relied on. The analysis records this reproduction as a
validation gate (reproduces_ctrl1c_map = true). This is provable numerical equivalence to the
original routine, reported as such.

| map | a | b | raw log P(Yes) at p = 0.5 |
|---|---|---|---|
| Orin 4B (F16 GGUF, this study) | 0.114932 | 1.174287 | -10.2173 |
| H100 4B (StudyCTRL1c) | 0.114603 | 1.140751 | (reference) |
| 32B (StudyCTRL1c) | 0.129472 | 1.848187 | (reference) |

The Orin 4B slope is within 0.0003 of the H100 4B slope (same model, same decision geometry);
the intercept is higher by 0.0335, absorbing the device's stack-induced score offset.

### Apply to the dense scores and tier residual

The map was applied to the 42,014 StudyORIN1 Orin dense scores (mean calibrated log-odds
-0.0814). The 601 DEV clips and the 300 dense-evaluation clips are disjoint (overlap 0;
confirms no leakage from fit to evaluation). Residual tier offset (calibrated Orin 4B minus
calibrated 32B), measured on both sets where both tiers were run: -0.0171 log-odds on D3 DEV
(n = 6,010), and -0.0155 log-odds on the 300 dense-evaluation clips (n = 42,014; StudyD14b
holds 32BI N=1 dense 0.25-s traces for all 300 clips in results/dashcam/study_d14b/, used by
StudyCTRL1/1b/1c). Both are far tighter than StudyCTRL1c's H100 4B residual of -0.1197. After
device-specific calibration the Orin 4B is essentially tier-aligned with the 32B, and the D3
DEV fit set and the dense evaluation set agree on this residual to within 0.002 log-odds.

The map is saved as results/dashcam/study_orin2/orin2_calibration.json in StudyCTRL1c's JSON
format.

## Part 2: warm recall latency without image re-send

### Step 1: is there a server-native path? (source investigation, c0fd786)

No server-native HTTP path can append a question to a cached multimodal prefix without
re-sending the image bytes. Evidence from the source:

- The server reuses KV by common prefix: get_common_prefix matches image chunks by id
  (server-common.cpp:760-782), and that id is the sha256 of the decoded image bytes
  (mtmd-helper.cpp:382). With cache_prompt true and identical history, the history images'
  KV is reused and their CLIP encode is skipped (encode_mtmd_chunk only runs past n_past,
  server-context.cpp:4228).
- But the id is computed server-side from the bytes; there is no client-facing
  reference-by-id API. The chat endpoint accepts only data:...;base64 or a URL
  (server-chat.cpp:422-488), so every call re-uploads and re-preprocesses all history image
  bytes. That transport and preprocessing is the cost StudyORIN1 Part 3 attributed to the
  API artifact; KV reuse does not remove it.
- Slot save/restore exists (--slot-save-path, /slots/:id?action=save|restore,
  llama_state_seq_save_file/load_file) but offers no "restore slot, decode only these new
  tokens, sample" primitive: a /completion continuation still rebuilds the full prompt
  (history image chunks required), so it cannot omit the images.

Therefore an in-process harness was required.

### Step 2: the in-process harness

experiments/device/orin2_harness/warm_recall.cpp links the same build's libllama and libmtmd
(same commit c0fd786, same GGUF and mmproj, same -c 57344, flash attention on, greedy seed 0,
n_batch 2048 / n_ubatch 512 as the server). It evaluates the frame history once into the
context KV (the warm state), then for each question rewinds the KV to the history and
evaluates only the question tokens over the cached context, decoding the answer. Token
identity with the server is by construction: the single user turn header + N images + question
is chat-templated (jinja) and tokenized with the same mtmd pipeline, so the harness's
warm-chunk prefix plus its question-text suffix equal the server's full prompt. Build
instructions: experiments/device/orin2_harness/build.sh.

### Step 3: equivalence gate (before any timing)

On 3 DEV questions at 11k, harness versus server:

| check | result |
|---|---|
| prompt tokens (harness history + suffix vs server prompt_tokens) | exact match (11215 / 11152 / 11155) |
| answer token / argmax | identical (C / A / B) |
| top-20 token sets | identical (20 / 20 shared) |
| max abs first-token logprob diff | 0.100 / 0.077 / 0.064 nats |
| server self-jitter (two fresh re-encodes) | 0.0 |

Tolerance provenance (reported, not a pre-registered pass): the gate was set to 0.05 nats
BEFORE any data. It failed at 0.064 to 0.100 nats. After seeing that result it was replaced
(user-approved) by 0.15 nats. Reason: the server is bit-deterministic (self-jitter 0.0),
prompts are token-identical, and the answer token and full top-20 set are identical; the
residual gap is the harness batching the image encode differently from the server, and image
encoding is part of building the warm history, which is excluded from the timed path. This is
a post-hoc tolerance change, labelled as such, not a pre-registered pass. The equivalence
criteria used: token-identical prompt AND identical answer token AND identical top-20 set AND
logprob diff <= 0.15 nats.

### Step 4: cross-path verification on all 40 (one request at a time, exclusive GPU)

Exclusivity recorded: no frame-transfer or Part 1 scoring process ran during either batch; the
only GPU process during the server batch was our own llama-server. The harness batch and the
server batch never ran concurrently. Clock pinned on all harness and all server measurements.

The cross-path check (user-defined for this study) requires: total prompt tokens identical,
answer token identical, and harness question-tokens-evaluated >= server question-tokens-evaluated
(the harness never does less work). Result on all 40: 0 total mismatches, 0 answer mismatches,
0 cases of the harness doing less work. PASS.

Boundary offset: the harness evaluates +15 tokens (16 to 18 on 6 of 40 questions, 0 on 2) that
the server counts as cached. Cause: the server's prefix cache extends about 15
template/vision-wrapper tokens past the last image into the cached region, while the harness
evaluates them as part of the question. Totals are conserved (history_tokens + suffix ==
server prompt_tokens on every question). The harness therefore evaluates a superset of the
server's question, biasing against the device.

Bias from the boundary offset, in ms next to TTFT p50:

| history | offset (median) | harness ms/question-token | bias added to harness TTFT | at server rate |
|---|---|---|---|---|
| 11k | 15 | 1.056 | +15.8 ms | +15.2 ms |
| 28k | 15 | 1.627 | +24.4 ms | +22.8 ms |

The bias makes the harness slightly SLOWER than the true device cost (conservative toward the
device): the reported harness TTFT already includes about 16 to 24 ms of extra question-eval
that the server charges to its cache.

### Step 5: latency, both paths, same day, side by side

TTFT and total latency p50 / p90 / min / max (seconds), 20 DEV questions per size:

| history | path | TTFT p50 | p90 | min | max | total p50 | p90 | min | max |
|---|---|---|---|---|---|---|---|---|---|
| 11k | harness | 0.146 | 0.173 | 0.121 | 0.243 | 0.209 | 0.267 | 0.184 | 0.417 |
| 11k | server | 1.416 | 1.447 | 1.350 | 1.487 | 1.481 | 1.538 | 1.415 | 1.683 |
| 28k | harness | 0.225 | 0.265 | 0.182 | 0.365 | 0.302 | 0.400 | 0.259 | 0.565 |
| 28k | server | 3.433 | 3.501 | 3.315 | 3.582 | 3.512 | 3.642 | 3.394 | 3.804 |

Decomposition (model question-eval vs everything else):

| history | server model work (prompt_ms) | server everything_else (TTFT - prompt_ms) | harness model work (= its TTFT) |
|---|---|---|---|
| 11k | 124.9 ms | 1285.2 ms | 146.2 ms |
| 28k | 188.1 ms | 3245.1 ms | 225.4 ms |

Ratio server path / harness path:

| history | TTFT p50 ratio | total p50 ratio |
|---|---|---|
| 11k | 9.7x | 7.1x |
| 28k | 15.2x | 11.6x |

The server TTFT is about 91% everything_else (image re-send and re-parse), only about 9%
model work. The harness removes the everything_else and its model work (146 / 225 ms) matches
the server's model work (125 / 188 ms, harness higher by the boundary-offset bias plus the
first-token sample). Warm recall still scales with history on the harness path, only through
attention over the cached context: harness TTFT p50 rises from 0.146 s (11k) to 0.225 s (28k),
a slope of 0.0322 ms per cached history position. This refutes the "near-free" assumption for
device warm recall while showing the growth is model attention, not the API artifact.

D61 conclusion: the harness path is the device's warm-recall baseline for the policy
evaluation; the server path is an API artifact and must not be used as the device baseline.

## Mechanism verification

Part 1 (calibration). Causal chain: the Orin F16 GGUF stack differs from the H100 vLLM BF16
stack, so absolute log P(Yes) scores shift while ordering is preserved (StudyD15, StudyORIN1);
a single-feature Platt map on log P(Yes) removes the device's offset so calibrated device
probabilities are comparable across tiers for the quality SLO.
- Implementing quantity and evidence: Orin vs H100 Pearson 0.9418 (not 1.0) with mean offset
  -0.2576 shows the stack difference is present and non-zero; the Platt map has non-zero slope
  (0.1149) and a device-specific intercept (1.1743 vs H100 1.1408). Negative control: applying
  the H100 map would leave the device's -0.2576 offset uncorrected; the device map reduces the
  tier residual to -0.0171. Alternative explanation considered: the offset could be label noise,
  but the 0.9418 correlation over 6,010 requests and the clean separability (which breaks
  unregularized fitting) rule that out. PASS.

Part 2 (warm recall). Causal chain: the server's warm-recall TTFT is dominated by re-sending
and re-parsing the image history each call (physical Context Inertia measured through an API
artifact, not device compute); a path that evaluates the history once and only the question
thereafter exposes the device's true warm-recall cost.
- Implementing quantity and evidence: server everything_else is 1285 ms (11k) and 3245 ms (28k),
  about 91% of TTFT, and it grows with history size (more images to re-send); server model work
  (prompt_ms) is only 125 / 188 ms. Negative control: the harness disables the re-send mechanism
  and TTFT collapses to 146 / 225 ms while its model work matches the server's model work,
  confirming the re-send was the driver and the model computation is unchanged. Alternative
  explanation considered: the gap could be harness under-computation (evaluating fewer tokens),
  but the cross-path check shows token-identical totals, identical answers, and the harness
  evaluating a 15-token superset, so the harness does at least as much model work. PASS.

## Results consistency check

1. Cross-check against committed measurements.

| quantity | this run | prior run | source | agree |
|---|---|---|---|---|
| Orin vs H100 4B Pearson | 0.9418 | 0.9426 | StudyORIN1-dense H100 agreement | yes |
| Orin 4B Platt slope a | 0.114932 | 0.114603 (H100 4B) | StudyCTRL1c | same model, expected near-equal |
| server warm TTFT p50 11k / 28k | 1.416 / 3.433 s | 1.41 / 3.43 s | StudyORIN1-dense Part 3 | yes (same-day reproduction) |
| server warm model work | 125 / 188 ms | 0.13 to 0.19 s | StudyORIN1-dense Part 3 | yes |

2. Physical plausibility. Harness question-eval rate about 0.95 tokens/ms (about 950 tokens/s)
for roughly 123 question tokens over an 11k cached context; the server's prompt_ms implies the
same (123 tokens / 124.9 ms = 985 tokens/s). The two paths agree on the device prefill rate, and
neither exceeds a committed device curve by more than 2x. No caching artifact: Part 1 is cold
(cache_prompt false); Part 2 warm is labelled warm and both paths reuse the history KV.

3. Distribution sanity. Latencies are reported with full p50 / p90 / min / max spreads; harness
TTFT at 11k varies 0.121 to 0.243 s across 20 questions (no suspicious constants). The boundary
offset varies 0 / 15 / 16 / 17 / 18 across questions, consistent with BPE merging at the image or
text boundary rather than a fixed short-circuit.

4. Definition audit. "Warm recall", "TTFT", "history tokens", "question tokens evaluated" use the
StudyORIN1 Part 3 and StudyE8 definitions. "Cached history tokens" = server cache_n = harness
history_tokens (KV tokens, not M-RoPE positions; the two differ for 2D images, which is why the
harness history_n_past of 1620 corresponds to 11,014 KV tokens). "DEV split" = StudyB amendment 2
(sha256(video_id) lowest 30%).

5. Claim linkage. Part 1 bears on the quality SLO: calibrated device probabilities are required to
compare the device arm against the cloud arm under a common quality threshold. Part 2 bears on the
physical component of Context Inertia (FORMULATION: transfer and reconstruction latency that grows
with context length): it supplies the device warm-recall cost curve the policy simulator needs, and
corrects a prior measurement that used an API artifact. Neither measures a FORMULATION-scoped-out
object (no cross-tier KV transfer is claimed; the harness keeps a single device context in memory).

6. Proxy validity. The harness is not a proxy for the device computation; it is the device
computation on the same libllama and libmtmd, same weights and mmproj. The only approximation is the
15-token cache/eval boundary offset, which is quantified (Part 2 Step 4) and biases against the
device; it is reported as a limitation, not used to make the device look faster.

## Limitations

- The Orin 4B tier residual is reported on both the D3 DEV fit set (-0.0171) and the 300-clip dense
  evaluation set (-0.0155), where StudyD14b holds 32BI N=1 dense traces; the two agree to within
  0.002 log-odds.
- The equivalence-gate logprob tolerance was changed post-hoc from 0.05 to 0.15 nats after seeing
  the data (reported in full under Part 2 Step 3).
- The harness evaluates a median of 15 extra question tokens per call (the cache/eval boundary),
  adding about 16 to 24 ms to its TTFT; this is conservative (it makes the device look slower).

## Files

- results/dashcam/study_orin2/orin2_d3dev_scores.jsonl.gz (6,010 Orin D3 DEV scores)
- results/dashcam/study_orin2/orin2_calibration.json (the Orin 4B Platt map)
- results/dashcam/study_orin2/study_orin2_part1_analysis.json (gates, validation, tier residual)
- results/dashcam/study_orin2/orin2_part1_frame_gate.json, orin2_meta.json
- results/dashcam/study_orin2/orin2_server.log.gz, orin2_tegrastats.jsonl.gz
- results/cost/study_orin2/orin2_warm_recall.jsonl (40 per-question rows, both paths)
- results/cost/study_orin2/orin2_warm_recall_summary.json (latency, decomposition, bias, ratio)
- results/cost/study_orin2/orin2_equivalence_gate.json, orin2_warm_crosscheck.json, orin2_exclusivity.json
- experiments/dashcam/study_orin2_calibrate.py (Part 1), experiments/dashcam/study_orin2_warm.py (Part 2 driver)
- experiments/device/orin2_harness/warm_recall.cpp, build.sh (in-process harness)
