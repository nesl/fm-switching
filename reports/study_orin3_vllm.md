# StudyORIN3-vllm: the device tier under vLLM

Pre-registered 2026-11-17 (EXPERIMENTS.md row StudyORIN3-vllm), before any scoring. This study
measures the Jetson AGX Orin device tier under vLLM, the same serving-engine family as the H100
cloud (and the stack NVIDIA's own Jetson VLM tutorial uses), so the device baseline does not
depend on having chosen llama.cpp. Same model, same inputs, same device as StudyORIN1-dense and
StudyORIN2-stack. Only the serving stack changes.

## Headline

1. **The score gap StudyORIN1 attributed to the device was a serving-stack artifact.** Under
   vLLM the Orin 4B matches the H100 vLLM 4B almost exactly (Pearson 0.9962, mean signed offset
   +0.004 log units on 6,010 requests). The same device under llama.cpp sat about one log unit
   off (StudyORIN1/ORIN2). The vLLM-on-Orin Platt map (a=0.114703, b=1.141292) reproduces the
   H100 4B map (a=0.114603, b=1.140751), so StudyCTRL1c's H100 calibration is reusable on the
   Orin under vLLM, which it was not under llama.cpp (map 0.114932, 1.174287).

2. **Warm recall via vLLM prefix cache is 8.9x / 15.0x faster than recompute, but is not
   output-identical to recompute.** The equivalence gate was a pre-registered FAILURE that
   revealed a real property of the cache path: the first-token logprobs drift about 0.25 nats
   (argmax answer stable 39/40). The device warm-recall baseline used elsewhere remains the
   StudyORIN2 in-process llama.cpp harness, which is both faster and output-equivalent within
   0.15 nats. The vLLM numbers here are a serving-stack sensitivity result.

## Stack

- Hardware: Jetson AGX Orin 64 GB, JetPack 6.2.2, L4T R36.5.0, CUDA 12.6.
- Serving: vLLM 0.20.0+cu126 (official jetson-ai-lab jp6/cu126 wheel), native venv at
  /home/nesl/orin3_vllm_venv, Python 3.10.12. torch 2.11.0+cu126 (jetson), torchvision 0.26.0
  (jetson), transformers 5.20.2, tokenizers 0.23.3, xgrammar 0.1.32 (jetson), triton 3.8.0.
  Attention backend FLASH_ATTN (chosen by vLLM from FLASH_ATTN, FLASHINFER, TRITON_ATTN,
  FLEX_ATTENTION). Full freeze in results/cost/study_orin3/orin3_pip_freeze.txt.
- Model: Qwen/Qwen3-VL-4B-Instruct, revision ebb281ec70b05090aa6165b016eac8ec08e71b17 (the same
  revision the H100 4BI used in StudyD3), dtype bfloat16 (closest no-quantization match to the
  llama.cpp F16 GGUF). Weights in /dev/shm (RAM, 8.3 GB; disk was too tight at 8.6 GB free).
- Serial device operation: server flags max-num-seqs 1, one request in flight at all times.
  Greedy, seed 0, max_tokens 8 (Part 1) / 64 (Part 2), top-20 logprobs. GPU clock pinned
  1.3005 GHz (1300500000 Hz), logged per request; MAXN. Non-default vLLM args recorded in each
  meta JSON: dtype bfloat16, max_model_len 32768, gpu_memory_utilization 0.4 (Part 1) / 0.5
  (Part 2), enforce_eager, limit_mm_per_prompt image 9 (Part 1) / 600 (Part 2), seed 0.
- Prefix caching ON for all score and efficient-path runs; OFF for the Part 1 cold check and the
  Part 2 re-send path.

### Native-install dependency workarounds (and whether they can affect the numbers)

The official jetson-ai-lab vLLM 0.20.0 wheel does not pin torch, so a plain install pulled PyPI's
torch 2.14.1+cu130, which cannot use the Orin's CUDA 12.6 driver. The working stack required five
fixes, each applied as an implementation fix (not a methodological change):

1. Replace PyPI torch 2.14.1+cu130 with the jetson torch 2.11.0+cu126 (the torch the jetson index
   pairs with vLLM 0.20.0). Numerics: this is the intended, supported torch; no effect beyond
   making CUDA usable.
2. Supply libcudss.so.0 via nvidia-cudss-cu12 0.8.0.10 (JetPack base CUDA omits cuDSS); the jetson
   torch links it. Not on the inference path for this workload.
3. xgrammar 0.1.32 from the jetson index (PyPI's 0.2.9 requires apache-tvm-ffi>=0.1.11, which
   conflicts with vLLM's pin apache-tvm-ffi==0.1.9). xgrammar is the guided-decoding backend; we
   decode greedily with no grammar, so it is imported but not exercised.
4. torchvision 0.26.0 from the jetson index (required by the Qwen3-VL image processor). Standard
   pairing with torch 2.11.0.
5. FLASHINFER_DISABLE_VERSION_CHECK=1. This skips only an import-time version-equality assertion
   between flashinfer-python (0.6.15.post1) and flashinfer-cubin (0.6.13). vLLM selected FLASH_ATTN
   as the attention backend, not FLASHINFER, and greedy decoding (temperature 0 = argmax) does not
   invoke flashinfer sampling kernels, so flashinfer is not on the inference path and the bypass
   cannot affect numerics or latency.

## Part 1: monitoring scores and latency (one frame per request)

Requests: the 6,010 StudyD3 DEV N=1 requests (601 clips x 10 event-anchored offsets), identical
to the set StudyORIN2 scored (request-id set verified equal to orin2_d3dev_scores.jsonl.gz), plus
a 2,000-request sample of the StudyORIN1 D14b evaluation requests. Request contract byte-identical
to StudyD15: header "The following is 1 dashcam frame.", one SMALL 768x432 PNG, the Nexar query.
Every request's single frame was sha256-verified against the D3 / D14b frame manifests before
scoring (gate: 6,010/6,010 and 2,000/2,000, 0 missing, 0 mismatch).

Sampling of the 2,000: StudyORIN1 scored all 42,014 N=1 requests on the 0.25-s dense grid, but
only the 10,660 integer-second frames are resident on the Orin (the fractional-second frames were
cleaned up after StudyORIN1). Per the brief's "frames as available" rule, the sample is drawn from
the ORIN1-scored requests whose frame is present (the integer-second subset), stratified by
clip-level label (positive/negative) proportional to the available pool, seed 0: 1,025 positive +
975 negative, base rate 0.5125 (available pool 0.5126). Stated as a restriction, not hidden.

Sanity (both sets): 0 null scores, 0 neither, 0 errors; clock pinned 1.3005 GHz on every row;
prompt_tokens 378 on every request, matching StudyD15's N=1 token count exactly.

### Score agreement (same requests)

| comparison | n | Pearson | mean signed (vLLM minus other) | median abs diff |
|---|---|---|---|---|
| vLLM-Orin vs H100 vLLM 4B (d3dev) | 6,010 | 0.9962 | +0.0043 | 0.25 |
| vLLM-Orin vs llama.cpp-Orin (d3dev) | 6,010 | 0.9417 | +0.2619 | 1.03 |
| vLLM-Orin vs H100 vLLM 4B (d14b) | 2,000 | 0.9958 | -0.0127 | 0.25 |
| vLLM-Orin vs llama.cpp-Orin1 (d14b) | 2,000 | 0.9393 | +0.2530 | 1.03 |

Under the same engine family the Orin matches the H100 4B to a mean of 0.004 to 0.013 log units.
The residual against llama.cpp-on-Orin (+0.26) is exactly the stack offset StudyORIN2 measured
from the other side (llama.cpp-Orin was -0.2576 below the H100 4B); vLLM-Orin lands on the H100.

### Challenge AP on the 2,000 sample (request-level AP, score ranked vs clip label)

vLLM-Orin 0.5695, llama.cpp-Orin1 0.5728, H100 vLLM 4B 0.5682. The ranking is stack-invariant: the
0.26-log monotone offset barely moves AP. (This is a flat per-request AP for a cross-stack ranking
comparison, not StudyCTRL1b's streaming/horizon mAP.)

### Calibration

Fitted with the committed StudyCTRL1c routine imported unchanged (ctrl1c_calibrate.fit_platt,
Newton/IRLS). Reproduction check: refitting on the H100 4B D3 DEV scores recovers a=0.114603,
b=1.140751 exactly. The vLLM-on-Orin map is a=0.114703, b=1.141292 (raw log P(Yes) at p=0.5 =
-9.95), essentially the H100 4B map; the llama.cpp-on-Orin map was a=0.114932, b=1.174287 (raw log
P(Yes) at p=0.5 = -10.22). Tier residual (calibrated vLLM-4B minus calibrated H100-32B on the
6,010 d3dev requests, where both tiers exist): -0.0178 log-odds, matching StudyORIN2's llama.cpp
value -0.0171 and far from the H100-4B reference -0.1197. Map saved to
results/dashcam/study_orin3/orin3_calibration.json.

### Latency (warm header)

vLLM TTFT p50 0.255 s / total 0.315 s (d3dev); the StudyORIN2 llama.cpp Part 1 latencies on the
same requests were TTFT p50 0.471 s / total 0.526 s (cache_prompt false, cold). vLLM is faster per
request. Caching state is stated explicitly: vLLM prefix caching was ON, but for one-frame
monitoring the shared header prefix is about 10 tokens, shorter than one 16-token KV block, so no
block is cacheable before the differing image. Labelled "warm header".

Cold check (user-required): the server was restarted once with prefix caching OFF and a seeded
200-request subsample re-timed (seed 0, ids in orin3_part1_d3dev_coldcheck_ids.json). Warm TTFT
p50 0.254 s vs cold 0.250 s, a difference of -1.65% at p50 (cold marginally faster, within noise),
below 5%. Header caching does not affect the Part 1 comparison.

## Part 2: warm recall latency (StudyORIN2 design)

Same StudyE7 D2 longest session (video 9902221866524366, 578 frames available) warmed to about
11k and 28k tokens, the same 20 DEV questions (sember_split dev set), TTFT/total one request at a
time, clock pinned, exclusive GPU (process list recorded in each path's meta JSON). vLLM emits 90
tokens per 352x256 E7 frame (measured), so 11k = 122 frames (11,215 prompt tokens) and 28k = 311
frames (28,225), the same frame counts StudyORIN2 used. Two paths, both through vLLM's OpenAI
server:

- **efficient**: prefix caching ON, history images carry stable per-image uuids (vLLM 0.20.0
  chat_utils supports a uuid per media item, with --mm-processor-cache). A priming request warms
  the KV, then each question is served with the history prefix as a cache hit.
- **re-send**: prefix caching OFF, each question re-sends and re-processes the full history (the
  StudyORIN1 Part 3 / stateless-client path).

Cache served from cache, verified per request (vLLM 0.20.0 does not populate
usage.prompt_tokens_details.cached_tokens in the OpenAI API, so the per-request prefix-cache-hit
tokens are read from the /metrics counters vllm:prefix_cache_hits and _queries):

| size | prompt tokens | efficient cache-hit tokens (median) | re-send cache-hit (median) |
|---|---|---|---|
| 11k | 11,215 | 11,144 (99.4%) | 0 |
| 28k | 28,225 | 28,160 (99.8%) | 0 |

### Latency (TTFT, one request at a time, clock pinned)

| size | efficient p50 | efficient p90 | re-send p50 | re-send p90 | ratio p50 |
|---|---|---|---|---|---|
| 11k | 0.657 s | 0.672 s | 5.861 s | 5.903 s | 8.9x |
| 28k | 1.596 s | 1.638 s | 23.917 s | 24.003 s | 15.0x |

Totals track TTFT closely (efficient total p50 0.719 s / 1.656 s; re-send 5.922 s / 23.988 s).
The prefix cache removes the history recompute; the speedup (8.9x at 11k, 15.0x at 28k) grows with
context length, as expected since the recompute cost grows with history length while the cached
question suffix does not.

### Side-by-side with StudyORIN2 (TTFT p50)

| path | 11k | 28k |
|---|---|---|
| StudyORIN2 llama.cpp in-process harness | 0.146 s | 0.225 s |
| StudyORIN2 llama.cpp server (image re-send) | 1.416 s | 3.433 s |
| StudyORIN3 vLLM efficient (prefix cache) | 0.657 s | 1.596 s |
| StudyORIN3 vLLM re-send (recompute) | 5.861 s | 23.917 s |

The device warm-recall baseline used elsewhere (design log D61) remains the StudyORIN2 in-process
harness: it is the fastest path and is output-equivalent to the server within 0.15 nats with
identical answers and top-20 sets and server self-jitter 0.0. The vLLM numbers are a serving-stack
sensitivity result. The vLLM efficient path (0.657 / 1.596 s) is slower than the in-process
harness because, like the llama.cpp server, vLLM's OpenAI API has no decode-only-suffix primitive:
the full base64 history is re-sent and re-parsed on every call even when its KV is a cache hit, and
the server runs eager (no CUDA graphs). It is faster than its own re-send path and than the
llama.cpp server at 28k. The vLLM re-send path is much slower than the llama.cpp server because
with prefix caching OFF vLLM recomputes the entire history every call with no multimodal-processor
cache, whereas the llama.cpp server in StudyORIN1/ORIN2 kept a prompt cache.

### Equivalence gate: pre-registered FAILURE, and it is real

The gate (pre-registered at 0.05 nats, not changed) asked whether the efficient path is
output-identical to re-send. It FAILED, and the failure is a real property of vLLM's prefix-cache
path, not a tolerance quibble:

- Answer (argmax) agreement across all 40 questions: 39/40 (one flip at 11k, efficient D vs
  re-send A).
- Top-20 token set identical: 31/40.
- First-token max logprob difference per question: p50 0.222, p90 0.372, max 0.451, min 0.071
  nats. All 40 exceed 0.05; 27/40 exceed even StudyORIN2's post-hoc 0.15.

Two isolating tests show the drift is from the cache path, not from relaunching the server:

- Self-jitter: the same question sent twice to one server (caching OFF) gives an identical answer,
  identical top-20 set, and max logprob diff 0.0. Within a launch the engine is bit-deterministic.
- Within-launch cold vs warm: on one caching-ON server, the same question computed cold (cache-hit
  0 tokens, TTFT 8.496 s) then warm (cache-hit 11,136 tokens, TTFT 0.666 s) gives the same answer
  but a different top-20 set and a max logprob diff of 0.251 nats.

Mechanism: on a cache hit, the new query tokens attend over stored KV in a different reduction
order than a fresh prefill; over 11k to 28k tokens of bf16 and FLASH_ATTN with chunked prefill the
floating-point non-associativity accumulates to about 0.25 nats in the first-token logits, enough
to flip a borderline multiple-choice answer (1 of 40). Unlike StudyORIN2's in-process harness,
which was output-equivalent to the server within 0.15 nats, vLLM's efficient path is not
output-identical to recompute. We do NOT raise the tolerance; the gate is reported as a
pre-registered failure that revealed a caching-numerics property.

Open follow-up (user-deferred, not run): whether a different vLLM attention backend (TRITON_ATTN
or FLASHINFER), disabling chunked prefill, or fp32 logits yields a numerically exact cache path.

## Mechanism verification

**Step 1 - causal chains.** Part 1: if the one-log-unit StudyORIN1 device-vs-H100 score gap is a
serving-stack property (llama.cpp vs vLLM) rather than a device-fidelity property, then running
the device under vLLM (same engine family as the H100) must move the device scores onto the H100
vLLM 4B scores while the device hardware and inputs are unchanged, and the device's own vLLM Platt
map must then equal the H100 4B map. Part 2: if warm recall avoids recomputing the history by
reusing cached KV, then a prefix-cache hit on the history reduces the per-question work to the
question suffix, reducing TTFT, and disabling the cache must restore the full-recompute TTFT.

**Step 2 - instantiate.**

| causal link | implementing quantity | value / range | varies as expected | evidence |
|---|---|---|---|---|
| stack identity drives the score offset | mean signed score diff vLLM-Orin vs H100 4B, vs vLLM-Orin vs llama.cpp-Orin | +0.004 vs +0.262 | yes | the offset is present against llama.cpp and absent against H100 |
| device vLLM map equals H100 map | Platt (a,b) | (0.1147,1.1413) vs H100 (0.1146,1.1408) vs llama.cpp (0.1149,1.1743) | yes | vLLM-Orin map sits on H100, not on llama.cpp-Orin |
| cache hit removes history recompute | prefix-cache-hit tokens per question | 11,144 / 28,160 (efficient) vs 0 (re-send) | yes | /metrics delta per request |
| recompute avoided reduces TTFT | TTFT p50 | 0.657 / 1.596 s (efficient) vs 5.861 / 23.917 s (re-send) | yes | 8.9x / 15.0x |

No link is absent, zero, or constant where the claim needs it to vary.

**Step 3 - trace one unit.** d3dev request 00004_-3.0_N1: one 768x432 PNG, prompt_tokens 378
(matches StudyD15), first token "No", top-20 present, p_yes 6.8e-08, score -16.50, TTFT 0.268 s,
clock 1300500000 Hz, error none. Part 2 warm unit (11k, question 0): prompt_tokens 11,215,
prefix-cache-hit 11,144 tokens, TTFT 0.657 s, clock pinned; the matching cold unit computed the
same 11,215 tokens at TTFT 8.5 s with 0 cache hit.

**Step 4 - negative control.** Part 1: the H100-map reproduction is the control for the fitting
routine (refit on H100 scores recovers the published map exactly, so the routine is not
manufacturing the vLLM-H100 agreement). Part 2: disabling the mechanism under test (prefix caching
OFF, the re-send path) collapses the result: cache-hit tokens go to 0 and TTFT rises from 0.657 s
to 5.861 s (11k) and from 1.596 s to 23.917 s (28k), confirming the cache, not under-computation,
drives the efficient-path latency.

**Step 5 - alternative explanations.** The vLLM-H100 agreement (Part 1) could in principle be a
coincidence of calibration rather than true score agreement; it is distinguished by the raw
agreement before any fit (Pearson 0.9962, mean 0.004 on raw log P(Yes)), which the fit does not
touch. The Part 2 speedup could be produced by (a) the prefix cache avoiding history recompute
[claimed], or (b) a shorter prompt in the efficient path; (b) is ruled out because both paths send
identical prompts (11,215 / 28,225 tokens) and the only difference is the cache-hit token count
(99.4-99.8% vs 0).

## Results consistency check (six checks)

1. **Cross-check against committed measurements.** vLLM-Orin vs llama.cpp-Orin Pearson 0.9417
   agrees with StudyORIN1's device-vs-H100 0.9426 and StudyORIN2's 0.9418 (all about 0.94). The
   +0.262 vLLM-minus-llama.cpp offset reconciles with StudyORIN2's -0.2576 llama.cpp-minus-H100
   offset (vLLM-Orin = H100, llama.cpp-Orin = H100 - 0.26). Tier residual -0.0178 agrees with
   StudyORIN2's -0.0171. Part 2 re-send TTFT at 11k (5.861 s) is of the same order as, and larger
   than, the llama.cpp server 1.416 s (vLLM has no prompt cache when caching is OFF, and no mm
   cache, so it recomputes more). No disagreement exceeds 2x on a shared quantity after the stack
   difference is accounted for.
2. **Physical plausibility.** Part 1 TTFT 0.255 s for a 378-token prefill implies about 1,500
   tok/s; the Part 2 cold prime prefills 11,215 tokens in 8.5 s (about 1,320 tok/s) and 28,225 in
   18 s (about 1,570 tok/s), all consistent and none faster than a plausible device prefill rate,
   so no caching artifact is masquerading as compute. The efficient warm TTFT (0.657 s for an
   11,215-token prompt) would be impossible as a cold prefill (it would need about 17,000 tok/s),
   which is exactly why the cache-hit verification is required and was done.
3. **Distribution sanity.** Latencies are reported with p50/p90/min/max; the efficient 11k TTFT
   ranges 0.648 to 0.697 s (not a suspicious constant), re-send 11k 5.809 to 5.914 s. Score
   distributions span the full range (p_yes 1e-8 to near 1). The logprob-drift distribution
   (p50 0.222, max 0.451) is reported, not collapsed to a single number.
4. **Definition audit.** "N=1 request" = header + one 768x432 small PNG + Nexar query, 378 tokens,
   identical to StudyD15 and the D3 vLLM runs. "score" = log(max(p_yes, 1e-12)), the StudyD14b /
   d15 definition. "warm recall" = the StudyORIN2 design (same E7 session, 11k/28k, 20 DEV
   questions). "challenge AP" is defined in-line as a flat request-level AP and explicitly
   distinguished from StudyCTRL1b's streaming mAP. Tokens-per-frame differs by stack (llama.cpp 90,
   vLLM measured 90 for these 352x256 frames and about 340 for 768x432), so the 11k/28k targets are
   token budgets, not frame counts; the frame counts (122/311) happen to match StudyORIN2.
5. **Claim linkage.** Part 1 bears on the device-tier fidelity claim (FORMULATION fidelity audit):
   it shows the audited device fidelity is serving-stack dependent and that under vLLM the device
   equals the cloud 4B. Part 2 bears on Context Inertia's physical component (reconstruction
   latency): it quantifies warm-recall TTFT under vLLM and shows the efficient path's fidelity
   caveat. Neither measures an object FORMULATION scopes out.
6. **Proxy validity.** Prefix-cache-hit tokens from /metrics are used as the proxy for "history
   served from cache" because vLLM does not expose cached_tokens in the OpenAI API; the proxy is
   the engine's own cache-hit counter and is valid (its delta equals the prompt tokens on a full
   hit, 11,144 of 11,215). The 2,000 D14b sample is the integer-second subset of the dense grid (a
   frame-availability restriction), valid for a cross-stack score and AP comparison on the same
   requests but not a claim about the full 0.25-s grid; stated as a limitation.

## Limitations

- The 2,000 D14b sample is the integer-second subset of the ORIN1-scored 0.25-s grid (only those
  frames are resident on the Orin); the cross-stack comparison is on the same requests, but it is
  not the full dense grid.
- vLLM 0.20.0 does not report cached_tokens in the OpenAI API; cache verification uses the
  /metrics prefix-cache counters instead.
- Part 2 efficient path still re-sends and re-parses the base64 history each call (OpenAI API has
  no decode-only-suffix primitive) and runs eager, so its absolute TTFT is not the device's
  minimum warm-recall cost; the StudyORIN2 in-process harness is.
- The equivalence gate failed (reported as a finding, not a pass). The exact-cache-config
  follow-up was not run.
- The flashinfer version check was bypassed; justified above as off the inference path.

## Files

New:
- experiments/device/study_orin3_vllm_part1.py (Part 1 gate/score/coldcheck)
- experiments/device/study_orin3_analyse.py (Part 1 analysis)
- experiments/device/study_orin3_vllm_warm.py (Part 2 efficient/resend/analyse)
- experiments/device/orin3_serve.sh (server launcher)
- results/dashcam/study_orin3/: orin3_d3dev_scores.jsonl, orin3_d14b_scores.jsonl,
  orin3_d3dev_coldcheck_scores.jsonl, orin3_calibration.json,
  study_orin3_part1_d3dev_analysis.json, study_orin3_part1_d14b_analysis.json,
  orin3_part1_d3dev_frame_gate.json, orin3_part1_d14b_frame_gate.json,
  orin3_part1_d3dev_setmeta.json, orin3_part1_d14b_setmeta.json,
  orin3_part1_d3dev_coldcheck_ids.json
- results/cost/study_orin3/: orin3_pip_freeze.txt, orin3_stage1_stack.json,
  orin3_warm_efficient.jsonl, orin3_warm_resend.jsonl, orin3_warm_efficient_meta.json,
  orin3_warm_resend_meta.json, orin3_warm_analysis.json, orin3_warm_equivalence.json
- reports/study_orin3_vllm.md (this report)

Single targeted insertions: research/EXPERIMENTS.md (pre-registration row, then verdict),
results/INDEX.md, research/STATUS.md.
