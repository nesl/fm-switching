# StudyA1 — comparability ledger

**Date:** 2026-11-04 · **Host:** flash, CPU only · **E-id:** StudyA1 (`research/EXPERIMENTS.md`) · **No inference was run.**

Every cell we cite, with the facts actually recorded in committed files. A field that is not recorded reads `UNKNOWN` — nothing here is inferred. Machine-readable copy: `results/audit/comparability_ledger.json`.


## 1. Counts

| classification | comparisons |
|---|---|
| IDENTICAL_INPUT | 6 |
| STACK_DIFFERENT | 4 |
| REALLOCATED_BUDGET | 3 |
| STRICT_ADDITION | 1 |
| FORMAT_DIFFERENT | 1 |

41 cells ledgered across 8 experiments; 11 comparisons classified (labels are not exclusive).


## 2. Sanity checks (recomputed from the raw request files)

| check | expected | recomputed | n paired | abs diff | within 0.01 pp |
|---|---|---|---|---|---|
| H1 - K3 | -5.80 | -5.7988 (32.54 vs 38.34) | 845 | 0.0012 | YES |
| H2 - K1 | -9.35 | -9.3491 (30.18 vs 39.53) | 845 | 0.0009 | YES |
| D2 - H3 (RH4 paired set) | +1.79 | +1.7878 (39.57 vs 37.78) | 839 | 0.0022 | YES |
| K1 - K3 | +1.18 | +1.1834 (39.53 vs 38.34) | 845 | 0.0034 | YES |
| H2 - H1 | -2.37 | -2.3669 (30.18 vs 32.54) | 845 | 0.0031 | YES |

## 3. Pairwise comparisons

### H1-K3  ·  IDENTICAL_INPUT

- **Arms:** `Clean.H1` vs `R1.K3`
- **Cited as:** study_clean_comparisons.md -5.80 pp
- **Can identify:** model capability at fixed input (4B-I vs 32B-I)
- **Cannot be used to claim:** say anything about the device tier: both arms ran on the H100, and H1 is 4B on cloud hardware, not a device measurement
- **Evidence:** StudyClean input_identity: prompt tokens 845/845 exact, H1 replays K3's own requests; same vLLM 0.31.0 FA3, both greedy 512

### H2-K1  ·  IDENTICAL_INPUT

- **Arms:** `Clean.H2` vs `R1.K1`
- **Cited as:** study_clean_comparisons.md -9.35 pp
- **Can identify:** model capability at fixed input on the RICH construction
- **Cannot be used to claim:** separate capability from host: K1 ran on GPU 3 and H2 on GPU 1. The SAN cell (30/30 letters) is the evidence that the card does not move greedy letters, so this is a near-identical, not an identical, host
- **Evidence:** prompt tokens 845/845 exact; same stack and decoding

### D2-H3  ·  STRICT_ADDITION + STACK_DIFFERENT

- **Arms:** `RH4.D2` vs `Clean.H3`
- **Cited as:** study_clean_comparisons.md +1.79 pp overall, +21.28 OLDER, -3.15 INSIDE
- **Can identify:** the value of history at a fixed model, stride, frame size and format: H3 is exactly D2's frames filtered to t >= qt-120, so D2 strictly contains H3's frames
- **Cannot be used to claim:** separate history from the header (H3 keeps D2's 'from the session start' header, which is false for H3 when qt > 120); and it cannot be read as a clean cold-latency contrast, because RH4's server ran with prefix_caching=True while StudyClean's ran with it OFF
- **Evidence:** tokens INSIDE 5,622 vs 12,710; OLDER 5,603 vs 14,857; qt<=120 3,505 = 3,505 (identical input, built-in null)

### K1-K3  ·  REALLOCATED_BUDGET

- **Arms:** `R1.K1` vs `R1.K3`
- **Cited as:** audit (a) +1.18 pp; +17.53 OLDER, +10.18 OVERLAP, -5.80 INSIDE
- **Can identify:** nothing on its own as a single factor: RICH vs RECENT moves the window, the frame count and the resolution together under one token budget
- **Cannot be used to claim:** attribute the sign flip to history length alone; the audit already records that window, frame count and resolution move together
- **Evidence:** same model, stack, host, greedy t=0.0; audit comparability table

### H2-H1  ·  REALLOCATED_BUDGET

- **Arms:** `Clean.H2` vs `Clean.H1`
- **Cited as:** study_clean_comparisons.md -2.37 pp
- **Can identify:** the same RICH-vs-RECENT reallocation as K1-K3, but read by 4B-I
- **Cannot be used to claim:** be used as a capability claim; both arms are the same model
- **Evidence:** same server, same stack, same decoding, same 845 questions

### C2-C1  ·  REALLOCATED_BUDGET

- **Arms:** `device.C2` vs `device.C1`
- **Cited as:** audit (b) -0.47 pp; +19.59 OLDER, -5.56 INSIDE
- **Can identify:** the RICH-vs-RECENT reallocation on the device runtime (llama.cpp F16)
- **Cannot be used to claim:** be compared directly against K1-K3 as a device-vs-cloud statement; it only shows the sign pattern replicates
- **Evidence:** same GGUF, same server flags, same greedy decoding, same 845 questions

### K1/K3-vs-4B-I(StudyO)  ·  STACK_DIFFERENT + FORMAT_DIFFERENT

- **Arms:** `R1.K1` vs `(StudyO 4B-I fa2 arms)`
- **Cited as:** audit (c) +8.99 / +5.56 pp
- **Can identify:** nothing cleanly
- **Cannot be used to claim:** support any capability claim: model size, serving stack (vLLM vs HF flash_attention_2) and kernel all move at once. The audit labels it CROSS-STACK
- **Evidence:** audit (c); median frame counts matched (231/231, 121/121)

### ERQA C-A_h100  ·  IDENTICAL_INPUT

- **Arms:** `R.C` vs `R.A_h100`
- **Cited as:** audit (d) +6.00 pp
- **Can identify:** model capability (32B-I vs 4B-I) on identical questions, same host, same sdpa kernel, same greedy decoding
- **Cannot be used to claim:** say anything about a device: both arms are cloud-hardware runs; A_h100 is the 4B model on the H100
- **Evidence:** audit (d), n=400, same trials file

### MVRobo C-H4  ·  IDENTICAL_INPUT + STACK_DIFFERENT

- **Arms:** `S2.C` vs `Clean.H4`
- **Cited as:** study_clean_comparisons.md +10.22 pp
- **Can identify:** model capability on an identical prompt set and an identical HF stack
- **Cannot be used to claim:** be called same-host: arm C ran on h100nvl GPU 3 and H4 on GPU 1. Input tokens are 401/401 equal
- **Evidence:** StudyS2 prompt and manifest reused unchanged; HF 5.10.2, torch 2.8.0+cu128, sdpa, batch 1, bf16, greedy 512

### MVRobo C-R4  ·  IDENTICAL_INPUT + STACK_DIFFERENT

- **Arms:** `S2.C` vs `(StudyR4 4B-I, RTX 3090 Ti)`
- **Cited as:** audit (e) +10.97 pp
- **Can identify:** model capability on identical questions, but across hosts
- **Cannot be used to claim:** be used as a same-host capability number; the audit labels it CROSS-HOST (H100 NVL vs RTX 3090 Ti). StudyClean H4 supersedes it with an identical-stack +10.22
- **Evidence:** audit (e), n=401

### H5 Orin-H100  ·  IDENTICAL_INPUT

- **Arms:** `DevFast.N37 / DevOne.N1` vs `Clean.H5.*`
- **Cited as:** study_clean_comparisons.md 15.8-16.7x (4B), 7.1x at N=1
- **Can identify:** the hardware and stack gap in TTFT at a fixed payload: the payload bytes are sha256-identical (4,380/4,380 frames) and the prompt token counts match on both stacks
- **Cannot be used to claim:** be read as an end-to-end device-vs-cloud latency: the H100 side is localhost with NO NETWORK, and it is a shared host. The runtimes also differ (llama.cpp vs vLLM 0.31.0), so hardware and stack are not separated
- **Evidence:** h5_input_identity 4,380 frames matched; cached_tokens 0 on every request; Orin warm rows (input_tokens=1) excluded


## 3b. Comparisons that changed from how they were previously described

**The audit's "the replay has not happened" is now out of date**

`reports/audit_2026_11_03.md` §Comparability states that StudyDevOne built the identical-input manifest *so that* the H100 could replay byte-identical payloads, and that **"that replay has not happened"**. It has: StudyClean H5 ran later the same day and replayed all 120 questions at N in {37,18,9,1} with **4,380/4,380 frame sha256 matching the manifest**. So the record now does contain an identical-input device-vs-cloud comparison - but a **latency** one only. The audit's stronger sentence, that no device-vs-cloud *accuracy* comparison uses identical input, still holds: H5's accuracy column is n=120 and labelled indicative.

**MV-RoboBench 32B vs 4B: cross-host +10.97 superseded by identical-stack +10.22**

Audit (e) reports +10.97 pp for arm C minus StudyR4's 4B-I, labelled CROSS-HOST (H100 NVL vs RTX 3090 Ti). StudyClean H4 re-ran the 4B arm on StudyS2's own prompt and manifest with an identical HF stack, giving **+10.22 pp**. The cross-host number should no longer be the cited one. Note H4 and arm C still differ by GPU (GPU 1 vs GPU 3), so even +10.22 is IDENTICAL_INPUT + STACK_DIFFERENT, not a same-host result.

**ERQA arm A is an a6000 run reused from StudyK, not an H100 run**

`study_r_trials_h100nvl.jsonl` rows for arm A carry `_reused_from = 'study_q_arm_E (=study_k INSTRUCT)'` and `_hardware = 'a6000'`. The file name says h100nvl, so arm A is easy to misread as an H100 cell. Any 32B-vs-4B ERQA contrast built on arm **A** is CROSS-HOST. The audit's (d) comparison is correct because it uses **A_h100**, which the run meta confirms on `NVIDIA H100 NVL` with `sdpa`.

**StudyRH4 served with prefix caching ON; StudyR1 and StudyClean served with it OFF**

`study_rh4_run_meta_h100nvl.json` records `prefix_caching: True`, while `study_r1_run_meta` and `study_clean_run_meta` both record `False`. Under greedy decoding this does not affect accuracy, so **D2 - H3 as an accuracy contrast is unaffected**. But it means no StudyRH4 timing number is a cold prefill, and a D2-vs-H3 latency reading would be comparing a prefix-cached server against a cold one. CLAUDE.md treats cache state as a methodological parameter, so this is recorded here rather than left implicit.

**K1 - K3 is REALLOCATED_BUDGET, not a history-length contrast**

The audit already notes that window, frame count and resolution move together between RICH and RECENT. The ledger makes that a label: K1-K3 and H2-H1 identify **no single factor**. The clean history contrast in the record is D2 - H3, where the model, stride, frame size and format are fixed and D2's frames strictly contain H3's.


## 4. Exclusions

| excluded | reason |
|---|---|
| E24, E24b, E24c | INVALID (audit 2026-11-03). E24/E24b compare disjoint single-point rules; E24c's policies share one value function and allocator and joint's candidate set strictly contains the decomposed policies', so the defect is the value function, not the action space. Excluded by instruction. |
| StudyI2 SPATIAL and TEMPORAL arms; StudyI3 TEMPORAL and its reanalysis | INVALID (audit 2026-11-03): these arms sample the FIRST N seconds, not the N seconds before the question. SPARSE is unaffected. |
| StudyD and StudyD2 (the Thinking studies) | INVALID (audit 2026-11-03): Thinking decoded greedily; all 240 and 420 repetition groups byte-identical. NOT the same object as RH4's D2 arm, which is canonical and IS in this ledger as RH4.D2. |
| StudyJ as a gate | INVALID (audit 2026-11-03): temp 0.6, 2048 budget, no stored scores. |

## 5. UNKNOWN fields that matter, and how to recover them

| field | cells with UNKNOWN | how it could be recovered |
|---|---|---|
| `vision_tokens` | 39 | recoverable for StudyR1/StudyRH4 from the inputs manifest (`grid_thw`, `image_tokens`); for StudyClean and the device cells it would need a re-tokenisation of the stored prompts (CPU only, no inference). |
| `quantization_dtype` | 25 | recoverable from the server command line in the run log (`logs/study_x_server_*.log`) or from the HF config dtype. |
| `input_frame_hashes` | 21 | only StudyDevOne recorded per-PNG sha256 (`results/device/identical_input_manifest.json`). For the other cells the frames were rendered on the fly and not hashed; they could be regenerated deterministically from the video ids and `frame_t`, then hashed, without any inference. |
| `header_or_template_hash` | 20 | recoverable by hashing the stored prompt text in the trials files; StudyRH4 records the header string explicitly. |
| `final_resolution` | 16 | recoverable from the inputs manifest (`final_hw` / `hw`) for StudyR1 and StudyRH4; for the device and StudyClean cells it would need the frame cache or a re-run of the image preprocessor. |
| `concurrency` | 9 | recoverable from the batched-mode request scheduler in the study script and from the `at` timestamps in the request records. |
| `prefix_cache` | 4 | not recorded anywhere; would need a re-run. |
| `max_tokens` | 4 | not recorded anywhere; would need a re-run. |
| `attention_backend` | 2 | not recorded anywhere; would need a re-run. |

## 6. The ledger

### `Clean.H1`

| field | value |
|---|---|
| experiment | StudyClean |
| cell | H1 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | S-EMBER |
| n | 845 |
| question-set hash | 6b1069d49418193d/n=845 |
| frame timestamps source | inherited from StudyR1 K3/K1 request construction |
| input frame hashes | UNKNOWN |
| frame count | median 121, range [7, 121] |
| final processed resolution | UNKNOWN |
| vision tokens | UNKNOWN |
| total prompt tokens | median 12437, range [1810, 12734] |
| input format | video (K3's own requests) |
| header / template hash | UNKNOWN |
| model | Qwen/Qwen3-VL-4B-Instruct |
| snapshot | ebb281ec70b05090aa6165b016eac8ec08e71b17 |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 1 |
| batching mode | batched |
| concurrency | UNKNOWN |
| decoding | temperature=0.0, max_tokens=512 |
| max tokens | 512 |
| prefix-cache state | False |
| timing boundary | batched - NOT VALID AS LATENCY |
| correctness definition | exact match of parsed letter vs correct_letter (`correct` field) |
| result file | results/cost/study_clean/study_clean_requests_h100nvl.jsonl.gz |
| accuracy_pct | 32.5444 |
| registry_hosts | h100nvl GPU 1 |
| question_text_hash | UNKNOWN |

### `Clean.H2`

| field | value |
|---|---|
| experiment | StudyClean |
| cell | H2 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | S-EMBER |
| n | 845 |
| question-set hash | 6b1069d49418193d/n=845 |
| frame timestamps source | inherited from StudyR1 K3/K1 request construction |
| input frame hashes | UNKNOWN |
| frame count | median 231, range [7, 256] |
| final processed resolution | UNKNOWN |
| vision tokens | UNKNOWN |
| total prompt tokens | median 12597, range [1810, 13196] |
| input format | video (K1's own requests) |
| header / template hash | UNKNOWN |
| model | Qwen/Qwen3-VL-4B-Instruct |
| snapshot | ebb281ec70b05090aa6165b016eac8ec08e71b17 |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 1 |
| batching mode | batched |
| concurrency | UNKNOWN |
| decoding | temperature=0.0, max_tokens=512 |
| max tokens | 512 |
| prefix-cache state | False |
| timing boundary | batched - NOT VALID AS LATENCY |
| correctness definition | exact match of parsed letter vs correct_letter (`correct` field) |
| result file | results/cost/study_clean/study_clean_requests_h100nvl.jsonl.gz |
| accuracy_pct | 30.1775 |
| registry_hosts | h100nvl GPU 1 |
| question_text_hash | UNKNOWN |

### `Clean.H3`

| field | value |
|---|---|
| experiment | StudyClean |
| cell | H3 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | S-EMBER |
| n | 845 |
| question-set hash | 6b1069d49418193d/n=845 |
| frame timestamps source | RH4 D2 frames filtered to t >= qt-120 |
| input frame hashes | UNKNOWN |
| frame count | median 60, range [4, 61] |
| final processed resolution | UNKNOWN |
| vision tokens | UNKNOWN |
| total prompt tokens | median 5600, range [511, 5928] |
| input format | separate images (RH4 D2 frames with t >= qt-120, D2 header kept) |
| header / template hash | UNKNOWN |
| model | Qwen/Qwen3-VL-32B-Instruct |
| snapshot | 0cfaf48183f594c314753d30a4c4974bc75f3ccb |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 1 |
| batching mode | batched |
| concurrency | UNKNOWN |
| decoding | temperature=0.0, max_tokens=512 |
| max tokens | 512 |
| prefix-cache state | False |
| timing boundary | batched - NOT VALID AS LATENCY |
| correctness definition | exact match of parsed letter vs correct_letter (`correct` field) |
| result file | results/cost/study_clean/study_clean_requests_h100nvl.jsonl.gz |
| accuracy_pct | 37.5148 |
| registry_hosts | h100nvl GPU 1 |
| question_text_hash | UNKNOWN |

### `Clean.H4`

| field | value |
|---|---|
| experiment | StudyClean |
| cell | H4 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | MV-RoboBench |
| n | 401 |
| question-set hash | a45860b77f9e4ded/n=401 |
| frame timestamps source | n/a (multi-view still images) |
| input frame hashes | UNKNOWN |
| frame count | median 3, range [3, 4] |
| final processed resolution | UNKNOWN |
| vision tokens | UNKNOWN |
| total prompt tokens | median 1032, range [374, 1079] |
| input format | separate images (StudyS2 prompt and manifest, unchanged) |
| header / template hash | f59c613fd7099b8e/n_distinct=96 |
| model | Qwen/Qwen3-VL-4B-Instruct |
| snapshot | ebb281ec70b05090aa6165b016eac8ec08e71b17 |
| quantization / dtype | bf16 |
| runtime + version | HF transformers 5.10.2 / torch 2.8.0+cu128 |
| attention backend | sdpa |
| host and GPU | h100nvl GPU 1 |
| batching mode | batch 1 |
| concurrency | 1 |
| decoding | greedy |
| max tokens | 512 |
| prefix-cache state | n/a (HF) |
| timing boundary | NOT VALID AS LATENCY (accuracy cell) |
| correctness definition | parsed letter vs ground truth; all 401 parsed 'direct' |
| result file | results/cost/study_clean/study_clean_h4_trials_h100nvl.jsonl.gz |
| registry_hosts | h100nvl GPU 1 |

### `Clean.H5.32BI_N18_p1`

| field | value |
|---|---|
| experiment | StudyClean |
| cell | H5 32BI N=18 pass 1 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | StudyDevOne identical-payload manifest |
| n | 120 |
| question-set hash | 64ae93d9d773527b/n=120 |
| frame timestamps source | StudyDevOne manifest ([t=Xs] markers verified) |
| input frame hashes | VERIFIED: 4380/4380 frame sha256 match the Orin manifest |
| frame count | median 18.0, range [14, 18] |
| final processed resolution | 560x560 PNG (byte-identical to the Orin payloads) |
| vision tokens | UNKNOWN |
| total prompt tokens | median 6123.0, range [4738, 6440] |
| input format | separate images |
| header / template hash | question text verified identical to the Orin manifest |
| model | Qwen/Qwen3-VL-32B-Instruct |
| snapshot | 0cfaf48183f594c314753d30a4c4974bc75f3ccb |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 1 (shared host, localhost, no network) |
| batching mode | serial, one request at a time |
| concurrency | 1 |
| decoding | greedy |
| max tokens | 512 |
| prefix-cache state | OFF; cached_tokens 0 on every request and cache-hit counters never grew |
| timing boundary | TTFT from immediately before sending a pre-serialized body to the first content token; localhost, shared host |
| correctness definition | indicative only, n=120 |
| result file | results/cost/study_clean/study_clean_h5_requests_h100nvl.jsonl.gz |
| ttft_s | median 1.3597000000000001, range [0.9965, 1.4581] |
| cached_tokens_max | 0 |
| registry_hosts | h100nvl GPU 1 |

### `Clean.H5.32BI_N18_p2`

| field | value |
|---|---|
| experiment | StudyClean |
| cell | H5 32BI N=18 pass 2 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | StudyDevOne identical-payload manifest |
| n | 120 |
| question-set hash | 64ae93d9d773527b/n=120 |
| frame timestamps source | StudyDevOne manifest ([t=Xs] markers verified) |
| input frame hashes | VERIFIED: 4380/4380 frame sha256 match the Orin manifest |
| frame count | median 18.0, range [14, 18] |
| final processed resolution | 560x560 PNG (byte-identical to the Orin payloads) |
| vision tokens | UNKNOWN |
| total prompt tokens | median 6123.0, range [4738, 6440] |
| input format | separate images |
| header / template hash | question text verified identical to the Orin manifest |
| model | Qwen/Qwen3-VL-32B-Instruct |
| snapshot | 0cfaf48183f594c314753d30a4c4974bc75f3ccb |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 1 (shared host, localhost, no network) |
| batching mode | serial, one request at a time |
| concurrency | 1 |
| decoding | greedy |
| max tokens | 512 |
| prefix-cache state | OFF; cached_tokens 0 on every request and cache-hit counters never grew |
| timing boundary | TTFT from immediately before sending a pre-serialized body to the first content token; localhost, shared host |
| correctness definition | indicative only, n=120 |
| result file | results/cost/study_clean/study_clean_h5_requests_h100nvl.jsonl.gz |
| ttft_s | median 1.35275, range [0.9772, 1.4228] |
| cached_tokens_max | 0 |
| registry_hosts | h100nvl GPU 1 |

### `Clean.H5.32BI_N1_p1`

| field | value |
|---|---|
| experiment | StudyClean |
| cell | H5 32BI N=1 pass 1 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | StudyDevOne identical-payload manifest |
| n | 120 |
| question-set hash | 64ae93d9d773527b/n=120 |
| frame timestamps source | StudyDevOne manifest ([t=Xs] markers verified) |
| input frame hashes | VERIFIED: 4380/4380 frame sha256 match the Orin manifest |
| frame count | median 1.0, range [1, 1] |
| final processed resolution | 560x560 PNG (byte-identical to the Orin payloads) |
| vision tokens | UNKNOWN |
| total prompt tokens | median 468.0, range [410, 794] |
| input format | separate images |
| header / template hash | question text verified identical to the Orin manifest |
| model | Qwen/Qwen3-VL-32B-Instruct |
| snapshot | 0cfaf48183f594c314753d30a4c4974bc75f3ccb |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 1 (shared host, localhost, no network) |
| batching mode | serial, one request at a time |
| concurrency | 1 |
| decoding | greedy |
| max tokens | 512 |
| prefix-cache state | OFF; cached_tokens 0 on every request and cache-hit counters never grew |
| timing boundary | TTFT from immediately before sending a pre-serialized body to the first content token; localhost, shared host |
| correctness definition | indicative only, n=120 |
| result file | results/cost/study_clean/study_clean_h5_requests_h100nvl.jsonl.gz |
| ttft_s | median 0.1475, range [0.1228, 0.1995] |
| cached_tokens_max | 0 |
| registry_hosts | h100nvl GPU 1 |

### `Clean.H5.32BI_N1_p2`

| field | value |
|---|---|
| experiment | StudyClean |
| cell | H5 32BI N=1 pass 2 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | StudyDevOne identical-payload manifest |
| n | 120 |
| question-set hash | 64ae93d9d773527b/n=120 |
| frame timestamps source | StudyDevOne manifest ([t=Xs] markers verified) |
| input frame hashes | VERIFIED: 4380/4380 frame sha256 match the Orin manifest |
| frame count | median 1.0, range [1, 1] |
| final processed resolution | 560x560 PNG (byte-identical to the Orin payloads) |
| vision tokens | UNKNOWN |
| total prompt tokens | median 468.0, range [410, 794] |
| input format | separate images |
| header / template hash | question text verified identical to the Orin manifest |
| model | Qwen/Qwen3-VL-32B-Instruct |
| snapshot | 0cfaf48183f594c314753d30a4c4974bc75f3ccb |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 1 (shared host, localhost, no network) |
| batching mode | serial, one request at a time |
| concurrency | 1 |
| decoding | greedy |
| max tokens | 512 |
| prefix-cache state | OFF; cached_tokens 0 on every request and cache-hit counters never grew |
| timing boundary | TTFT from immediately before sending a pre-serialized body to the first content token; localhost, shared host |
| correctness definition | indicative only, n=120 |
| result file | results/cost/study_clean/study_clean_h5_requests_h100nvl.jsonl.gz |
| ttft_s | median 0.14625, range [0.1223, 0.1876] |
| cached_tokens_max | 0 |
| registry_hosts | h100nvl GPU 1 |

### `Clean.H5.32BI_N37_p1`

| field | value |
|---|---|
| experiment | StudyClean |
| cell | H5 32BI N=37 pass 1 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | StudyDevOne identical-payload manifest |
| n | 120 |
| question-set hash | 64ae93d9d773527b/n=120 |
| frame timestamps source | StudyDevOne manifest ([t=Xs] markers verified) |
| input frame hashes | VERIFIED: 4380/4380 frame sha256 match the Orin manifest |
| frame count | median 37.0, range [14, 37] |
| final processed resolution | 560x560 PNG (byte-identical to the Orin payloads) |
| vision tokens | UNKNOWN |
| total prompt tokens | median 12420.0, range [4738, 12520] |
| input format | separate images |
| header / template hash | question text verified identical to the Orin manifest |
| model | Qwen/Qwen3-VL-32B-Instruct |
| snapshot | 0cfaf48183f594c314753d30a4c4974bc75f3ccb |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 1 (shared host, localhost, no network) |
| batching mode | serial, one request at a time |
| concurrency | 1 |
| decoding | greedy |
| max tokens | 512 |
| prefix-cache state | OFF; cached_tokens 0 on every request and cache-hit counters never grew |
| timing boundary | TTFT from immediately before sending a pre-serialized body to the first content token; localhost, shared host |
| correctness definition | indicative only, n=120 |
| result file | results/cost/study_clean/study_clean_h5_requests_h100nvl.jsonl.gz |
| ttft_s | median 3.01485, range [0.9848, 3.1117] |
| cached_tokens_max | 0 |
| registry_hosts | h100nvl GPU 1 |

### `Clean.H5.32BI_N37_p2`

| field | value |
|---|---|
| experiment | StudyClean |
| cell | H5 32BI N=37 pass 2 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | StudyDevOne identical-payload manifest |
| n | 120 |
| question-set hash | 64ae93d9d773527b/n=120 |
| frame timestamps source | StudyDevOne manifest ([t=Xs] markers verified) |
| input frame hashes | VERIFIED: 4380/4380 frame sha256 match the Orin manifest |
| frame count | median 37.0, range [14, 37] |
| final processed resolution | 560x560 PNG (byte-identical to the Orin payloads) |
| vision tokens | UNKNOWN |
| total prompt tokens | median 12420.0, range [4738, 12520] |
| input format | separate images |
| header / template hash | question text verified identical to the Orin manifest |
| model | Qwen/Qwen3-VL-32B-Instruct |
| snapshot | 0cfaf48183f594c314753d30a4c4974bc75f3ccb |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 1 (shared host, localhost, no network) |
| batching mode | serial, one request at a time |
| concurrency | 1 |
| decoding | greedy |
| max tokens | 512 |
| prefix-cache state | OFF; cached_tokens 0 on every request and cache-hit counters never grew |
| timing boundary | TTFT from immediately before sending a pre-serialized body to the first content token; localhost, shared host |
| correctness definition | indicative only, n=120 |
| result file | results/cost/study_clean/study_clean_h5_requests_h100nvl.jsonl.gz |
| ttft_s | median 2.9861500000000003, range [0.9758, 3.0848] |
| cached_tokens_max | 0 |
| registry_hosts | h100nvl GPU 1 |

### `Clean.H5.32BI_N9_p1`

| field | value |
|---|---|
| experiment | StudyClean |
| cell | H5 32BI N=9 pass 1 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | StudyDevOne identical-payload manifest |
| n | 120 |
| question-set hash | 64ae93d9d773527b/n=120 |
| frame timestamps source | StudyDevOne manifest ([t=Xs] markers verified) |
| input frame hashes | VERIFIED: 4380/4380 frame sha256 match the Orin manifest |
| frame count | median 9.0, range [9, 9] |
| final processed resolution | 560x560 PNG (byte-identical to the Orin payloads) |
| vision tokens | UNKNOWN |
| total prompt tokens | median 3130.5, range [3064, 3450] |
| input format | separate images |
| header / template hash | question text verified identical to the Orin manifest |
| model | Qwen/Qwen3-VL-32B-Instruct |
| snapshot | 0cfaf48183f594c314753d30a4c4974bc75f3ccb |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 1 (shared host, localhost, no network) |
| batching mode | serial, one request at a time |
| concurrency | 1 |
| decoding | greedy |
| max tokens | 512 |
| prefix-cache state | OFF; cached_tokens 0 on every request and cache-hit counters never grew |
| timing boundary | TTFT from immediately before sending a pre-serialized body to the first content token; localhost, shared host |
| correctness definition | indicative only, n=120 |
| result file | results/cost/study_clean/study_clean_h5_requests_h100nvl.jsonl.gz |
| ttft_s | median 0.6632, range [0.6324, 0.7203] |
| cached_tokens_max | 0 |
| registry_hosts | h100nvl GPU 1 |

### `Clean.H5.32BI_N9_p2`

| field | value |
|---|---|
| experiment | StudyClean |
| cell | H5 32BI N=9 pass 2 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | StudyDevOne identical-payload manifest |
| n | 120 |
| question-set hash | 64ae93d9d773527b/n=120 |
| frame timestamps source | StudyDevOne manifest ([t=Xs] markers verified) |
| input frame hashes | VERIFIED: 4380/4380 frame sha256 match the Orin manifest |
| frame count | median 9.0, range [9, 9] |
| final processed resolution | 560x560 PNG (byte-identical to the Orin payloads) |
| vision tokens | UNKNOWN |
| total prompt tokens | median 3130.5, range [3064, 3450] |
| input format | separate images |
| header / template hash | question text verified identical to the Orin manifest |
| model | Qwen/Qwen3-VL-32B-Instruct |
| snapshot | 0cfaf48183f594c314753d30a4c4974bc75f3ccb |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 1 (shared host, localhost, no network) |
| batching mode | serial, one request at a time |
| concurrency | 1 |
| decoding | greedy |
| max tokens | 512 |
| prefix-cache state | OFF; cached_tokens 0 on every request and cache-hit counters never grew |
| timing boundary | TTFT from immediately before sending a pre-serialized body to the first content token; localhost, shared host |
| correctness definition | indicative only, n=120 |
| result file | results/cost/study_clean/study_clean_h5_requests_h100nvl.jsonl.gz |
| ttft_s | median 0.66445, range [0.6362, 0.7191] |
| cached_tokens_max | 0 |
| registry_hosts | h100nvl GPU 1 |

### `Clean.H5.4BI_N18_p1`

| field | value |
|---|---|
| experiment | StudyClean |
| cell | H5 4BI N=18 pass 1 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | StudyDevOne identical-payload manifest |
| n | 120 |
| question-set hash | 64ae93d9d773527b/n=120 |
| frame timestamps source | StudyDevOne manifest ([t=Xs] markers verified) |
| input frame hashes | VERIFIED: 4380/4380 frame sha256 match the Orin manifest |
| frame count | median 18.0, range [14, 18] |
| final processed resolution | 560x560 PNG (byte-identical to the Orin payloads) |
| vision tokens | UNKNOWN |
| total prompt tokens | median 6123.0, range [4738, 6440] |
| input format | separate images |
| header / template hash | question text verified identical to the Orin manifest |
| model | Qwen/Qwen3-VL-4B-Instruct |
| snapshot | ebb281ec70b05090aa6165b016eac8ec08e71b17 |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 1 (shared host, localhost, no network) |
| batching mode | serial, one request at a time |
| concurrency | 1 |
| decoding | greedy |
| max tokens | 512 |
| prefix-cache state | OFF; cached_tokens 0 on every request and cache-hit counters never grew |
| timing boundary | TTFT from immediately before sending a pre-serialized body to the first content token; localhost, shared host |
| correctness definition | indicative only, n=120 |
| result file | results/cost/study_clean/study_clean_h5_requests_h100nvl.jsonl.gz |
| ttft_s | median 0.4891, range [0.3624, 0.5354] |
| cached_tokens_max | 0 |
| registry_hosts | h100nvl GPU 1 |

### `Clean.H5.4BI_N18_p2`

| field | value |
|---|---|
| experiment | StudyClean |
| cell | H5 4BI N=18 pass 2 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | StudyDevOne identical-payload manifest |
| n | 120 |
| question-set hash | 64ae93d9d773527b/n=120 |
| frame timestamps source | StudyDevOne manifest ([t=Xs] markers verified) |
| input frame hashes | VERIFIED: 4380/4380 frame sha256 match the Orin manifest |
| frame count | median 18.0, range [14, 18] |
| final processed resolution | 560x560 PNG (byte-identical to the Orin payloads) |
| vision tokens | UNKNOWN |
| total prompt tokens | median 6123.0, range [4738, 6440] |
| input format | separate images |
| header / template hash | question text verified identical to the Orin manifest |
| model | Qwen/Qwen3-VL-4B-Instruct |
| snapshot | ebb281ec70b05090aa6165b016eac8ec08e71b17 |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 1 (shared host, localhost, no network) |
| batching mode | serial, one request at a time |
| concurrency | 1 |
| decoding | greedy |
| max tokens | 512 |
| prefix-cache state | OFF; cached_tokens 0 on every request and cache-hit counters never grew |
| timing boundary | TTFT from immediately before sending a pre-serialized body to the first content token; localhost, shared host |
| correctness definition | indicative only, n=120 |
| result file | results/cost/study_clean/study_clean_h5_requests_h100nvl.jsonl.gz |
| ttft_s | median 0.49055000000000004, range [0.3518, 0.5452] |
| cached_tokens_max | 0 |
| registry_hosts | h100nvl GPU 1 |

### `Clean.H5.4BI_N1_p1`

| field | value |
|---|---|
| experiment | StudyClean |
| cell | H5 4BI N=1 pass 1 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | StudyDevOne identical-payload manifest |
| n | 120 |
| question-set hash | 64ae93d9d773527b/n=120 |
| frame timestamps source | StudyDevOne manifest ([t=Xs] markers verified) |
| input frame hashes | VERIFIED: 4380/4380 frame sha256 match the Orin manifest |
| frame count | median 1.0, range [1, 1] |
| final processed resolution | 560x560 PNG (byte-identical to the Orin payloads) |
| vision tokens | UNKNOWN |
| total prompt tokens | median 468.0, range [410, 794] |
| input format | separate images |
| header / template hash | question text verified identical to the Orin manifest |
| model | Qwen/Qwen3-VL-4B-Instruct |
| snapshot | ebb281ec70b05090aa6165b016eac8ec08e71b17 |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 1 (shared host, localhost, no network) |
| batching mode | serial, one request at a time |
| concurrency | 1 |
| decoding | greedy |
| max tokens | 512 |
| prefix-cache state | OFF; cached_tokens 0 on every request and cache-hit counters never grew |
| timing boundary | TTFT from immediately before sending a pre-serialized body to the first content token; localhost, shared host |
| correctness definition | indicative only, n=120 |
| result file | results/cost/study_clean/study_clean_h5_requests_h100nvl.jsonl.gz |
| ttft_s | median 0.0711, range [0.0534, 0.093] |
| cached_tokens_max | 0 |
| registry_hosts | h100nvl GPU 1 |

### `Clean.H5.4BI_N1_p2`

| field | value |
|---|---|
| experiment | StudyClean |
| cell | H5 4BI N=1 pass 2 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | StudyDevOne identical-payload manifest |
| n | 120 |
| question-set hash | 64ae93d9d773527b/n=120 |
| frame timestamps source | StudyDevOne manifest ([t=Xs] markers verified) |
| input frame hashes | VERIFIED: 4380/4380 frame sha256 match the Orin manifest |
| frame count | median 1.0, range [1, 1] |
| final processed resolution | 560x560 PNG (byte-identical to the Orin payloads) |
| vision tokens | UNKNOWN |
| total prompt tokens | median 468.0, range [410, 794] |
| input format | separate images |
| header / template hash | question text verified identical to the Orin manifest |
| model | Qwen/Qwen3-VL-4B-Instruct |
| snapshot | ebb281ec70b05090aa6165b016eac8ec08e71b17 |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 1 (shared host, localhost, no network) |
| batching mode | serial, one request at a time |
| concurrency | 1 |
| decoding | greedy |
| max tokens | 512 |
| prefix-cache state | OFF; cached_tokens 0 on every request and cache-hit counters never grew |
| timing boundary | TTFT from immediately before sending a pre-serialized body to the first content token; localhost, shared host |
| correctness definition | indicative only, n=120 |
| result file | results/cost/study_clean/study_clean_h5_requests_h100nvl.jsonl.gz |
| ttft_s | median 0.0704, range [0.0521, 0.0908] |
| cached_tokens_max | 0 |
| registry_hosts | h100nvl GPU 1 |

### `Clean.H5.4BI_N37_p1`

| field | value |
|---|---|
| experiment | StudyClean |
| cell | H5 4BI N=37 pass 1 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | StudyDevOne identical-payload manifest |
| n | 120 |
| question-set hash | 64ae93d9d773527b/n=120 |
| frame timestamps source | StudyDevOne manifest ([t=Xs] markers verified) |
| input frame hashes | VERIFIED: 4380/4380 frame sha256 match the Orin manifest |
| frame count | median 37.0, range [14, 37] |
| final processed resolution | 560x560 PNG (byte-identical to the Orin payloads) |
| vision tokens | UNKNOWN |
| total prompt tokens | median 12420.0, range [4738, 12520] |
| input format | separate images |
| header / template hash | question text verified identical to the Orin manifest |
| model | Qwen/Qwen3-VL-4B-Instruct |
| snapshot | ebb281ec70b05090aa6165b016eac8ec08e71b17 |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 1 (shared host, localhost, no network) |
| batching mode | serial, one request at a time |
| concurrency | 1 |
| decoding | greedy |
| max tokens | 512 |
| prefix-cache state | OFF; cached_tokens 0 on every request and cache-hit counters never grew |
| timing boundary | TTFT from immediately before sending a pre-serialized body to the first content token; localhost, shared host |
| correctness definition | indicative only, n=120 |
| result file | results/cost/study_clean/study_clean_h5_requests_h100nvl.jsonl.gz |
| ttft_s | median 1.0155, range [0.3925, 1.0887] |
| cached_tokens_max | 0 |
| registry_hosts | h100nvl GPU 1 |

### `Clean.H5.4BI_N37_p2`

| field | value |
|---|---|
| experiment | StudyClean |
| cell | H5 4BI N=37 pass 2 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | StudyDevOne identical-payload manifest |
| n | 120 |
| question-set hash | 64ae93d9d773527b/n=120 |
| frame timestamps source | StudyDevOne manifest ([t=Xs] markers verified) |
| input frame hashes | VERIFIED: 4380/4380 frame sha256 match the Orin manifest |
| frame count | median 37.0, range [14, 37] |
| final processed resolution | 560x560 PNG (byte-identical to the Orin payloads) |
| vision tokens | UNKNOWN |
| total prompt tokens | median 12420.0, range [4738, 12520] |
| input format | separate images |
| header / template hash | question text verified identical to the Orin manifest |
| model | Qwen/Qwen3-VL-4B-Instruct |
| snapshot | ebb281ec70b05090aa6165b016eac8ec08e71b17 |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 1 (shared host, localhost, no network) |
| batching mode | serial, one request at a time |
| concurrency | 1 |
| decoding | greedy |
| max tokens | 512 |
| prefix-cache state | OFF; cached_tokens 0 on every request and cache-hit counters never grew |
| timing boundary | TTFT from immediately before sending a pre-serialized body to the first content token; localhost, shared host |
| correctness definition | indicative only, n=120 |
| result file | results/cost/study_clean/study_clean_h5_requests_h100nvl.jsonl.gz |
| ttft_s | median 0.98425, range [0.3577, 1.0739] |
| cached_tokens_max | 0 |
| registry_hosts | h100nvl GPU 1 |

### `Clean.H5.4BI_N9_p1`

| field | value |
|---|---|
| experiment | StudyClean |
| cell | H5 4BI N=9 pass 1 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | StudyDevOne identical-payload manifest |
| n | 120 |
| question-set hash | 64ae93d9d773527b/n=120 |
| frame timestamps source | StudyDevOne manifest ([t=Xs] markers verified) |
| input frame hashes | VERIFIED: 4380/4380 frame sha256 match the Orin manifest |
| frame count | median 9.0, range [9, 9] |
| final processed resolution | 560x560 PNG (byte-identical to the Orin payloads) |
| vision tokens | UNKNOWN |
| total prompt tokens | median 3130.5, range [3064, 3450] |
| input format | separate images |
| header / template hash | question text verified identical to the Orin manifest |
| model | Qwen/Qwen3-VL-4B-Instruct |
| snapshot | ebb281ec70b05090aa6165b016eac8ec08e71b17 |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 1 (shared host, localhost, no network) |
| batching mode | serial, one request at a time |
| concurrency | 1 |
| decoding | greedy |
| max tokens | 512 |
| prefix-cache state | OFF; cached_tokens 0 on every request and cache-hit counters never grew |
| timing boundary | TTFT from immediately before sending a pre-serialized body to the first content token; localhost, shared host |
| correctness definition | indicative only, n=120 |
| result file | results/cost/study_clean/study_clean_h5_requests_h100nvl.jsonl.gz |
| ttft_s | median 0.24059999999999998, range [0.2207, 0.2617] |
| cached_tokens_max | 0 |
| registry_hosts | h100nvl GPU 1 |

### `Clean.H5.4BI_N9_p2`

| field | value |
|---|---|
| experiment | StudyClean |
| cell | H5 4BI N=9 pass 2 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | StudyDevOne identical-payload manifest |
| n | 120 |
| question-set hash | 64ae93d9d773527b/n=120 |
| frame timestamps source | StudyDevOne manifest ([t=Xs] markers verified) |
| input frame hashes | VERIFIED: 4380/4380 frame sha256 match the Orin manifest |
| frame count | median 9.0, range [9, 9] |
| final processed resolution | 560x560 PNG (byte-identical to the Orin payloads) |
| vision tokens | UNKNOWN |
| total prompt tokens | median 3130.5, range [3064, 3450] |
| input format | separate images |
| header / template hash | question text verified identical to the Orin manifest |
| model | Qwen/Qwen3-VL-4B-Instruct |
| snapshot | ebb281ec70b05090aa6165b016eac8ec08e71b17 |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 1 (shared host, localhost, no network) |
| batching mode | serial, one request at a time |
| concurrency | 1 |
| decoding | greedy |
| max tokens | 512 |
| prefix-cache state | OFF; cached_tokens 0 on every request and cache-hit counters never grew |
| timing boundary | TTFT from immediately before sending a pre-serialized body to the first content token; localhost, shared host |
| correctness definition | indicative only, n=120 |
| result file | results/cost/study_clean/study_clean_h5_requests_h100nvl.jsonl.gz |
| ttft_s | median 0.24355, range [0.2095, 0.2994] |
| cached_tokens_max | 0 |
| registry_hosts | h100nvl GPU 1 |

### `Clean.SAN`

| field | value |
|---|---|
| experiment | StudyClean |
| cell | SAN |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | S-EMBER |
| n | 30 |
| question-set hash | c0859b2ab840ffb3/n=30 |
| frame timestamps source | inherited from StudyR1 K3/K1 request construction |
| input frame hashes | UNKNOWN |
| frame count | median 121.0, range [47, 121] |
| final processed resolution | UNKNOWN |
| vision tokens | UNKNOWN |
| total prompt tokens | median 12439.5, range [11460, 12558] |
| input format | video (K3's own requests) |
| header / template hash | UNKNOWN |
| model | Qwen/Qwen3-VL-32B-Instruct |
| snapshot | 0cfaf48183f594c314753d30a4c4974bc75f3ccb |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 1 |
| batching mode | batched |
| concurrency | UNKNOWN |
| decoding | temperature=0.0, max_tokens=512 |
| max tokens | 512 |
| prefix-cache state | False |
| timing boundary | batched - NOT VALID AS LATENCY |
| correctness definition | exact match of parsed letter vs correct_letter (`correct` field) |
| result file | results/cost/study_clean/study_clean_requests_h100nvl.jsonl.gz |
| sanity | n=30, letters_match=30, required=29, passed=True, mismatches=[], prompt_tokens_equal=30 |
| accuracy_pct | 40.0 |
| registry_hosts | h100nvl GPU 1 |
| question_text_hash | UNKNOWN |

### `DevFast.N18`

| field | value |
|---|---|
| experiment | StudyDevFast |
| cell | 4B-I F16 N=18 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | S-EMBER frames |
| n | 119 |
| question-set hash | 1fbdf0d582961d49/n=119 |
| frame timestamps source | recorded per request where present; else UNKNOWN |
| input frame hashes | sha256 recorded in results/device/identical_input_manifest.json (StudyDevOne Part 1, 120 q x N in {37,18,9,1}) |
| frame count | median 18, range [14, 18] |
| final processed resolution | 560x560 PNG (per StudyDevOne manifest) |
| vision tokens | UNKNOWN |
| total prompt tokens | median 6123, range [4738, 6440] |
| input format | separate images (llama.cpp) |
| header / template hash | UNKNOWN |
| model | Qwen3VL-4B-Instruct-F16.gguf |
| snapshot | llama.cpp c0fd7862 |
| quantization / dtype | F16 GGUF |
| runtime + version | llama.cpp (llama-server) |
| attention backend | -fa on |
| host and GPU | jetson_orin (MAXN) |
| batching mode | serial |
| concurrency | 1 |
| decoding | greedy |
| max tokens | UNKNOWN |
| prefix-cache state | cache_prompt default ON - the first row of every cell is warm (input_tokens=1) and is EXCLUDED |
| timing boundary | TTFT, device-local, uncontended; medians exclude the warm row |
| correctness definition | n/a (latency cell) |
| result file | results/device/devfast_4bi_f16_n18.jsonl |
| n_excluded_warm_rows | 1 |
| registry_hosts | jetson_orin (MAXN mode 0, GPU 1.3005 GHz) |

### `DevFast.N37`

| field | value |
|---|---|
| experiment | StudyDevFast |
| cell | 4B-I F16 N=37 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | S-EMBER frames |
| n | 119 |
| question-set hash | 1fbdf0d582961d49/n=119 |
| frame timestamps source | recorded per request where present; else UNKNOWN |
| input frame hashes | sha256 recorded in results/device/identical_input_manifest.json (StudyDevOne Part 1, 120 q x N in {37,18,9,1}) |
| frame count | median 37, range [14, 37] |
| final processed resolution | 560x560 PNG (per StudyDevOne manifest) |
| vision tokens | UNKNOWN |
| total prompt tokens | median 12422, range [4738, 12520] |
| input format | separate images (llama.cpp) |
| header / template hash | UNKNOWN |
| model | Qwen3VL-4B-Instruct-F16.gguf |
| snapshot | llama.cpp c0fd7862 |
| quantization / dtype | F16 GGUF |
| runtime + version | llama.cpp (llama-server) |
| attention backend | -fa on |
| host and GPU | jetson_orin (MAXN) |
| batching mode | serial |
| concurrency | 1 |
| decoding | greedy |
| max tokens | UNKNOWN |
| prefix-cache state | cache_prompt default ON - the first row of every cell is warm (input_tokens=1) and is EXCLUDED |
| timing boundary | TTFT, device-local, uncontended; medians exclude the warm row |
| correctness definition | n/a (latency cell) |
| result file | results/device/devfast_4bi_f16_n37.jsonl |
| n_excluded_warm_rows | 1 |
| registry_hosts | jetson_orin (MAXN mode 0, GPU 1.3005 GHz) |

### `DevFast.N9`

| field | value |
|---|---|
| experiment | StudyDevFast |
| cell | 4B-I F16 N=9 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | S-EMBER frames |
| n | 119 |
| question-set hash | 1fbdf0d582961d49/n=119 |
| frame timestamps source | recorded per request where present; else UNKNOWN |
| input frame hashes | sha256 recorded in results/device/identical_input_manifest.json (StudyDevOne Part 1, 120 q x N in {37,18,9,1}) |
| frame count | median 9, range [9, 9] |
| final processed resolution | 560x560 PNG (per StudyDevOne manifest) |
| vision tokens | UNKNOWN |
| total prompt tokens | median 3131, range [3064, 3450] |
| input format | separate images (llama.cpp) |
| header / template hash | UNKNOWN |
| model | Qwen3VL-4B-Instruct-F16.gguf |
| snapshot | llama.cpp c0fd7862 |
| quantization / dtype | F16 GGUF |
| runtime + version | llama.cpp (llama-server) |
| attention backend | -fa on |
| host and GPU | jetson_orin (MAXN) |
| batching mode | serial |
| concurrency | 1 |
| decoding | greedy |
| max tokens | UNKNOWN |
| prefix-cache state | cache_prompt default ON - the first row of every cell is warm (input_tokens=1) and is EXCLUDED |
| timing boundary | TTFT, device-local, uncontended; medians exclude the warm row |
| correctness definition | n/a (latency cell) |
| result file | results/device/devfast_4bi_f16_n9.jsonl |
| n_excluded_warm_rows | 1 |
| registry_hosts | jetson_orin (MAXN mode 0, GPU 1.3005 GHz) |

### `DevOne.N1`

| field | value |
|---|---|
| experiment | StudyDevOne |
| cell | 4B-I F16 N=1 (cold) |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | StudyDevOne identical-payload manifest |
| n | 120 |
| question-set hash | 64ae93d9d773527b/n=120 |
| frame timestamps source | results/device/identical_input_manifest.json |
| input frame hashes | sha256 per PNG recorded in identical_input_manifest.json |
| frame count | median 1.0, range [1, 1] |
| final processed resolution | 560x560 PNG |
| vision tokens | UNKNOWN |
| total prompt tokens | median 468.0, range [410, 794] |
| input format | separate images (llama.cpp) |
| header / template hash | UNKNOWN |
| model | Qwen3VL-4B-Instruct-F16.gguf |
| snapshot | llama.cpp c0fd7862 |
| quantization / dtype | F16 GGUF |
| runtime + version | llama.cpp (llama-server) |
| attention backend | -fa on |
| host and GPU | jetson_orin (MAXN, GPU pinned 1.3005 GHz on all requests) |
| batching mode | serial |
| concurrency | 1 |
| decoding | greedy |
| max tokens | UNKNOWN |
| prefix-cache state | OFF (cache_prompt=false); cached_n = 0 on every request |
| timing boundary | TTFT, device-local, COLD, clock-pinned, uncontended |
| correctness definition | parsed letter vs correct_letter; accuracy 12.5 % (below chance) |
| result file | results/device/dev_one_n1.jsonl |
| ttft_s | median 0.506, range [0.483, 0.645] |
| registry_hosts | jetson_orin (MAXN mode 0, GPU 1.3005 GHz) |

### `R.A`

| field | value |
|---|---|
| experiment | StudyR |
| cell | arm A |
| status (registry) | canonical |
| status flag | **[CONFOUNDED (Thinking arms only) — audit 2026-11-03]** |
| workload | ERQA |
| n | 400 |
| question-set hash | b77a37482a5bc2a1/n=400 |
| frame timestamps source | n/a (ERQA still images) |
| input frame hashes | UNKNOWN |
| frame count | median 1.0, range [1, 16] |
| final processed resolution | UNKNOWN |
| vision tokens | UNKNOWN |
| total prompt tokens | median 822.5, range [114, 12350] |
| input format | separate images |
| header / template hash | UNKNOWN |
| model | Qwen/Qwen3-VL-4B-Instruct |
| snapshot | ebb281ec70b05090aa6165b016eac8ec08e71b17 |
| quantization / dtype | bf16 |
| runtime + version | HF transformers 5.10.2 / torch 2.8.0+cu128 |
| attention backend | UNKNOWN |
| host and GPU | a6000 |
| batching mode | batch 1 |
| concurrency | 1 |
| decoding | do_sample (False images), max_new_tokens (512 images) |
| max tokens | 512 |
| prefix-cache state | n/a (HF) |
| timing boundary | NOT VALID AS LATENCY |
| correctness definition | parsed letter vs ground truth |
| result file | results/erqa/study_r/study_r_trials_h100nvl.jsonl |
| registry_hosts | h100nvl (GPU 2 for C + D 1–23, GPU 3 thereafter; no contention) + reused a6000 |

### `R.A_h100`

| field | value |
|---|---|
| experiment | StudyR |
| cell | arm A_h100 |
| status (registry) | canonical |
| status flag | **[CONFOUNDED (Thinking arms only) — audit 2026-11-03]** |
| workload | ERQA |
| n | 400 |
| question-set hash | b77a37482a5bc2a1/n=400 |
| frame timestamps source | n/a (ERQA still images) |
| input frame hashes | UNKNOWN |
| frame count | median 1.0, range [1, 16] |
| final processed resolution | UNKNOWN |
| vision tokens | UNKNOWN |
| total prompt tokens | median 822.5, range [114, 12350] |
| input format | separate images |
| header / template hash | UNKNOWN |
| model | Qwen/Qwen3-VL-4B-Instruct |
| snapshot | ebb281ec70b05090aa6165b016eac8ec08e71b17 |
| quantization / dtype | bf16 |
| runtime + version | HF transformers 5.10.2 / torch 2.8.0+cu128 |
| attention backend | sdpa |
| host and GPU | NVIDIA H100 NVL |
| batching mode | batch 1 |
| concurrency | 1 |
| decoding | do_sample (False images), max_new_tokens (512 images) |
| max tokens | 512 |
| prefix-cache state | n/a (HF) |
| timing boundary | NOT VALID AS LATENCY |
| correctness definition | parsed letter vs ground truth |
| result file | results/erqa/study_r/study_r_trials_h100nvl.jsonl |
| registry_hosts | h100nvl (GPU 2 for C + D 1–23, GPU 3 thereafter; no contention) + reused a6000 |

### `R.B`

| field | value |
|---|---|
| experiment | StudyR |
| cell | arm B |
| status (registry) | canonical |
| status flag | **[CONFOUNDED (Thinking arms only) — audit 2026-11-03]** |
| workload | ERQA |
| n | 400 |
| question-set hash | b77a37482a5bc2a1/n=400 |
| frame timestamps source | n/a (ERQA still images) |
| input frame hashes | UNKNOWN |
| frame count | median 1.0, range [1, 16] |
| final processed resolution | UNKNOWN |
| vision tokens | UNKNOWN |
| total prompt tokens | median 824.5, range [116, 12352] |
| input format | separate images |
| header / template hash | UNKNOWN |
| model | Qwen/Qwen3-VL-4B-Thinking |
| snapshot | 1de27d8c51f12e819435303b9e84c4e25ba8401e |
| quantization / dtype | bf16 |
| runtime + version | HF transformers 5.10.2 / torch 2.8.0+cu128 |
| attention backend | UNKNOWN |
| host and GPU | a6000 |
| batching mode | batch 1 |
| concurrency | 1 |
| decoding | do_sample (False images), max_new_tokens (512 images) |
| max tokens | 512 |
| prefix-cache state | n/a (HF) |
| timing boundary | NOT VALID AS LATENCY |
| correctness definition | parsed letter vs ground truth |
| result file | results/erqa/study_r/study_r_trials_h100nvl.jsonl |
| registry_hosts | h100nvl (GPU 2 for C + D 1–23, GPU 3 thereafter; no contention) + reused a6000 |

### `R.C`

| field | value |
|---|---|
| experiment | StudyR |
| cell | arm C |
| status (registry) | canonical |
| status flag | **[CONFOUNDED (Thinking arms only) — audit 2026-11-03]** |
| workload | ERQA |
| n | 400 |
| question-set hash | b77a37482a5bc2a1/n=400 |
| frame timestamps source | n/a (ERQA still images) |
| input frame hashes | UNKNOWN |
| frame count | median 1.0, range [1, 16] |
| final processed resolution | UNKNOWN |
| vision tokens | UNKNOWN |
| total prompt tokens | median 822.5, range [114, 12350] |
| input format | separate images |
| header / template hash | UNKNOWN |
| model | Qwen/Qwen3-VL-32B-Instruct |
| snapshot | 0cfaf48183f594c314753d30a4c4974bc75f3ccb |
| quantization / dtype | bf16 |
| runtime + version | HF transformers 5.10.2 / torch 2.8.0+cu128 |
| attention backend | sdpa |
| host and GPU | NVIDIA H100 NVL |
| batching mode | batch 1 |
| concurrency | 1 |
| decoding | do_sample (False images), max_new_tokens (512 images) |
| max tokens | 512 |
| prefix-cache state | n/a (HF) |
| timing boundary | NOT VALID AS LATENCY |
| correctness definition | parsed letter vs ground truth |
| result file | results/erqa/study_r/study_r_trials_h100nvl.jsonl |
| registry_hosts | h100nvl (GPU 2 for C + D 1–23, GPU 3 thereafter; no contention) + reused a6000 |

### `R.D`

| field | value |
|---|---|
| experiment | StudyR |
| cell | arm D |
| status (registry) | canonical |
| status flag | CONFOUNDED (Thinking arm; sampled temperature 0.6 vs greedy Instruct comparators) - audit 2026-11-03 |
| workload | ERQA |
| n | 400 |
| question-set hash | b77a37482a5bc2a1/n=400 |
| frame timestamps source | n/a (ERQA still images) |
| input frame hashes | UNKNOWN |
| frame count | median 1.0, range [1, 16] |
| final processed resolution | UNKNOWN |
| vision tokens | UNKNOWN |
| total prompt tokens | median 824.5, range [116, 12352] |
| input format | separate images |
| header / template hash | UNKNOWN |
| model | Qwen/Qwen3-VL-32B-Thinking |
| snapshot | 7edd10ffd1196091948fb245ff63e406ccb2d4d1 |
| quantization / dtype | bf16 |
| runtime + version | HF transformers 5.10.2 / torch 2.8.0+cu128 |
| attention backend | sdpa |
| host and GPU | NVIDIA H100 NVL |
| batching mode | batch 1 |
| concurrency | 1 |
| decoding | do_sample=True, temperature=0.6, top_p=0.95, top_k=20, min_p=0.0, max_new_tokens=16384 |
| max tokens | 16384 |
| prefix-cache state | n/a (HF) |
| timing boundary | NOT VALID AS LATENCY |
| correctness definition | parsed letter vs ground truth |
| result file | results/erqa/study_r/study_r_trials_h100nvl.jsonl |
| registry_hosts | h100nvl (GPU 2 for C + D 1–23, GPU 3 thereafter; no contention) + reused a6000 |

### `R1.K1`

| field | value |
|---|---|
| experiment | StudyR1 |
| cell | K1 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | S-EMBER |
| n | 845 |
| question-set hash | 6b1069d49418193d/n=845 |
| frame timestamps source | inputs manifest `frame_t` (per question) |
| input frame hashes | UNKNOWN |
| frame count | median 231, range [7, 256] |
| final processed resolution | 352x256 (397 images), 416x320 (49 images), 384x288 (48 images), 352x288 (35 images), 448x352 (29 images), 480x384 (28 images) |
| vision tokens | UNKNOWN |
| total prompt tokens | median 12597, range [1810, 13196] |
| input format | video (121-256 frames as one video input) |
| header / template hash | UNKNOWN |
| model | Qwen/Qwen3-VL-32B-Instruct |
| snapshot | 0cfaf48183f594c314753d30a4c4974bc75f3ccb |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 3 |
| batching mode | batched |
| concurrency | UNKNOWN |
| decoding | temperature=0.0, max_tokens=512 |
| max tokens | 512 |
| prefix-cache state | False |
| timing boundary | batched mode - NOT VALID AS LATENCY (concurrent requests); timing5/single modes carry the latency numbers |
| correctness definition | exact match of parsed letter vs correct_letter (`correct` field) |
| result file | results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz |
| accuracy_pct | 39.5266 |
| registry_hosts | RECENT covers), with evidence_covered from the RECENT construction; holds if the CI excludes 0 and is positive. (4) CAPABILITY GAP: substitute K1 − 8B-I×RICH (same frames, bigger model, since 4B-I×RICH is absent), overall and split by RECENT evidence_covered, DiD and CI. (5) Escalation (local = 4B-I×RECENT, remote = K1): never / always / random / P4 top-e / question_time top-e / evidence oracle (top-e by farthest) / accuracy oracle at e ∈ {0.1, 0.2, 0.3}, as study_o_q4_analyze.py. CAVEAT, fixed in advance: 32B rows are vLLM on H100 and StudyO rows are HF on A6000. StudyX measured 5% answer drift between stacks for 32B-I, so cross-stack paired differences carry that noise. |
| question_text_hash | 38d13b4696b072a6/n_distinct=845 |

### `R1.K2`

| field | value |
|---|---|
| experiment | StudyR1 |
| cell | K2 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | S-EMBER |
| n | 845 |
| question-set hash | 6b1069d49418193d/n=845 |
| frame timestamps source | inputs manifest `frame_t` (per question) |
| input frame hashes | UNKNOWN |
| frame count | median 231, range [7, 256] |
| final processed resolution | 352x256 (397 images), 416x320 (49 images), 384x288 (48 images), 352x288 (35 images), 448x352 (29 images), 480x384 (28 images) |
| vision tokens | UNKNOWN |
| total prompt tokens | median 12599, range [1812, 13198] |
| input format | video (121-256 frames as one video input) |
| header / template hash | UNKNOWN |
| model | Qwen/Qwen3-VL-32B-Instruct |
| snapshot | 0cfaf48183f594c314753d30a4c4974bc75f3ccb |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 3 |
| batching mode | batched |
| concurrency | UNKNOWN |
| decoding | top_p=0.95, top_k=20, repetition_penalty=1.0, presence_penalty=0.0, temperature=1.0, min_p=0.0 |
| max tokens | 16384 |
| prefix-cache state | False |
| timing boundary | batched mode - NOT VALID AS LATENCY (concurrent requests); timing5/single modes carry the latency numbers |
| correctness definition | exact match of parsed letter vs correct_letter (`correct` field) |
| result file | results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz |
| note | second RICH cell in StudyR1; model/stage mapping to the 32BI vs 32BT server is UNKNOWN from run_meta alone |
| accuracy_pct | 33.8462 |
| registry_hosts | RECENT covers), with evidence_covered from the RECENT construction; holds if the CI excludes 0 and is positive. (4) CAPABILITY GAP: substitute K1 − 8B-I×RICH (same frames, bigger model, since 4B-I×RICH is absent), overall and split by RECENT evidence_covered, DiD and CI. (5) Escalation (local = 4B-I×RECENT, remote = K1): never / always / random / P4 top-e / question_time top-e / evidence oracle (top-e by farthest) / accuracy oracle at e ∈ {0.1, 0.2, 0.3}, as study_o_q4_analyze.py. CAVEAT, fixed in advance: 32B rows are vLLM on H100 and StudyO rows are HF on A6000. StudyX measured 5% answer drift between stacks for 32B-I, so cross-stack paired differences carry that noise. |
| question_text_hash | 38d13b4696b072a6/n_distinct=845 |

### `R1.K3`

| field | value |
|---|---|
| experiment | StudyR1 |
| cell | K3 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | S-EMBER |
| n | 845 |
| question-set hash | 6b1069d49418193d/n=845 |
| frame timestamps source | inputs manifest `frame_t` (per question) |
| input frame hashes | UNKNOWN |
| frame count | median 121, range [7, 121] |
| final processed resolution | 512x384 (642 images), 384x512 (44 images), 544x416 (25 images), 864x672 (21 images), 704x544 (11 images), 672x512 (10 images) |
| vision tokens | UNKNOWN |
| total prompt tokens | median 12437, range [1810, 12734] |
| input format | video (121-256 frames as one video input) |
| header / template hash | UNKNOWN |
| model | Qwen/Qwen3-VL-32B-Instruct |
| snapshot | 0cfaf48183f594c314753d30a4c4974bc75f3ccb |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 3 |
| batching mode | batched |
| concurrency | UNKNOWN |
| decoding | temperature=0.0, max_tokens=512 |
| max tokens | 512 |
| prefix-cache state | False |
| timing boundary | batched mode - NOT VALID AS LATENCY (concurrent requests); timing5/single modes carry the latency numbers |
| correctness definition | exact match of parsed letter vs correct_letter (`correct` field) |
| result file | results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz |
| accuracy_pct | 38.3432 |
| registry_hosts | RECENT covers), with evidence_covered from the RECENT construction; holds if the CI excludes 0 and is positive. (4) CAPABILITY GAP: substitute K1 − 8B-I×RICH (same frames, bigger model, since 4B-I×RICH is absent), overall and split by RECENT evidence_covered, DiD and CI. (5) Escalation (local = 4B-I×RECENT, remote = K1): never / always / random / P4 top-e / question_time top-e / evidence oracle (top-e by farthest) / accuracy oracle at e ∈ {0.1, 0.2, 0.3}, as study_o_q4_analyze.py. CAVEAT, fixed in advance: 32B rows are vLLM on H100 and StudyO rows are HF on A6000. StudyX measured 5% answer drift between stacks for 32B-I, so cross-stack paired differences carry that noise. |
| question_text_hash | 38d13b4696b072a6/n_distinct=845 |

### `RH4.D1`

| field | value |
|---|---|
| experiment | StudyRH4 |
| cell | D1 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | S-EMBER |
| n | 845 |
| question-set hash | 6b1069d49418193d/n=845 |
| frame timestamps source | inputs manifest `frame_t` (per question) |
| input frame hashes | UNKNOWN |
| frame count | median 116, range [4, 578] |
| final processed resolution | 288x224 (773 images), 224x288 (72 images) |
| vision tokens | median 7540, range [260, 37570] |
| total prompt tokens | median 7706, range [411, 32758] |
| input format | separate images (append-only, fixed 2 s stride) |
| header / template hash | f7917c678ab06f0e/n_distinct=1 |
| model | Qwen/Qwen3-VL-32B-Instruct |
| snapshot | 0cfaf48183f594c314753d30a4c4974bc75f3ccb |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 3 |
| batching mode | batched |
| concurrency | UNKNOWN |
| decoding | temperature=0.0, max_tokens=512 |
| max tokens | 512 |
| prefix-cache state | True |
| timing boundary | batched - NOT VALID AS LATENCY |
| correctness definition | exact match of parsed letter vs correct_letter (`correct` field) |
| result file | results/sember/study_rh4/study_rh4_requests_h100nvl.jsonl.gz |
| WARNING_prefix_cache | run_meta records prefix_caching=True for this server, unlike StudyR1 and StudyClean (both False). Accuracy under greedy decoding is unaffected, but no RH4 latency number is a cold prefill. |
| accuracy_pct | 36.568 |
| registry_hosts | h100nvl GPU 3 |
| question_text_hash | 38d13b4696b072a6/n_distinct=845 |

### `RH4.D2`

| field | value |
|---|---|
| experiment | StudyRH4 |
| cell | D2 |
| status (registry) | canonical |
| status flag | none (no audit flag on this row) |
| workload | S-EMBER |
| n | 845 |
| question-set hash | 6b1069d49418193d/n=845 |
| frame timestamps source | inputs manifest `frame_t` (per question) |
| input frame hashes | UNKNOWN |
| frame count | median 116, range [4, 578] |
| final processed resolution | 352x256 (773 images), 256x352 (72 images) |
| vision tokens | median 10440, range [360, 52020] |
| total prompt tokens | median 10584, range [511, 30701] |
| input format | separate images (append-only, fixed 2 s stride) |
| header / template hash | c918e56843b045eb/n_distinct=1 |
| model | Qwen/Qwen3-VL-32B-Instruct |
| snapshot | 0cfaf48183f594c314753d30a4c4974bc75f3ccb |
| quantization / dtype | UNKNOWN |
| runtime + version | vLLM 0.31.0 |
| attention backend | FlashAttention 3 |
| host and GPU | h100nvl GPU 3 |
| batching mode | batched |
| concurrency | UNKNOWN |
| decoding | temperature=0.0, max_tokens=512 |
| max tokens | 512 |
| prefix-cache state | True |
| timing boundary | batched - NOT VALID AS LATENCY |
| correctness definition | exact match of parsed letter vs correct_letter (`correct` field) |
| result file | results/sember/study_rh4/study_rh4_requests_h100nvl.jsonl.gz |
| WARNING_prefix_cache | run_meta records prefix_caching=True for this server, unlike StudyR1 and StudyClean (both False). Accuracy under greedy decoding is unaffected, but no RH4 latency number is a cold prefill. |
| accuracy_pct | 39.2899 |
| registry_hosts | h100nvl GPU 3 |
| question_text_hash | 38d13b4696b072a6/n_distinct=845 |

### `S2.C`

| field | value |
|---|---|
| experiment | StudyS2 |
| cell | arm C |
| status (registry) | canonical |
| status flag | **[CONFOUNDED (Thinking arm D only) — audit 2026-11-03]** |
| workload | MV-RoboBench |
| n | 401 |
| question-set hash | a45860b77f9e4ded/n=401 |
| frame timestamps source | n/a (multi-view still images) |
| input frame hashes | UNKNOWN |
| frame count | median 3, range [3, 4] |
| final processed resolution | UNKNOWN |
| vision tokens | UNKNOWN |
| total prompt tokens | median 1032, range [374, 1079] |
| input format | separate images (multi-view) |
| header / template hash | f59c613fd7099b8e/n_distinct=96 |
| model | Qwen/Qwen3-VL-32B-Instruct |
| snapshot | 0cfaf48183f594c314753d30a4c4974bc75f3ccb |
| quantization / dtype | bf16 |
| runtime + version | HF transformers (see run_meta) |
| attention backend | sdpa (asserted in report) |
| host and GPU | h100nvl GPU 3 |
| batching mode | batch 1 |
| concurrency | 1 |
| decoding | greedy |
| max tokens | 512 |
| prefix-cache state | n/a (HF, no prefix cache) |
| timing boundary | total_latency_ms recorded; contended - not a clean latency |
| correctness definition | answer_text letter vs ground truth |
| result file | results/erqa/study_s2/study_s2_trials_h100nvl.jsonl |
| registry_hosts | h100nvl (GPU 3) |

### `S2.D`

| field | value |
|---|---|
| experiment | StudyS2 |
| cell | arm D |
| status (registry) | canonical |
| status flag | **[CONFOUNDED (Thinking arm D only) — audit 2026-11-03]** |
| workload | MV-RoboBench |
| n | 401 |
| question-set hash | a45860b77f9e4ded/n=401 |
| frame timestamps source | n/a (multi-view still images) |
| input frame hashes | UNKNOWN |
| frame count | median 3, range [3, 4] |
| final processed resolution | UNKNOWN |
| vision tokens | UNKNOWN |
| total prompt tokens | median 1034, range [376, 1081] |
| input format | separate images (multi-view) |
| header / template hash | f59c613fd7099b8e/n_distinct=96 |
| model | Qwen/Qwen3-VL-32B-Thinking |
| snapshot | 7edd10ffd1196091948fb245ff63e406ccb2d4d1 |
| quantization / dtype | bf16 |
| runtime + version | HF transformers (see run_meta) |
| attention backend | sdpa (asserted in report) |
| host and GPU | h100nvl GPU 3 |
| batching mode | batch 1 |
| concurrency | 1 |
| decoding | greedy |
| max tokens | 512 |
| prefix-cache state | n/a (HF, no prefix cache) |
| timing boundary | total_latency_ms recorded; contended - not a clean latency |
| correctness definition | answer_text letter vs ground truth |
| result file | results/erqa/study_s2/study_s2_trials_h100nvl.jsonl |
| registry_hosts | h100nvl (GPU 3) |

### `device.C1`

| field | value |
|---|---|
| experiment | StudyDevAcc-llamacpp |
| cell | C1 |
| status (registry) | no distinct status column in this row; verdict cell reads: **CROSSOVER REPLICATES ON THE DEVICE RUNTIME.** 845 x 4 cells complete. A: C1 4B-I x RECENT 31.5% [28.4,34.7], C2 x RICH 31.0% [28.0,34.2], C3 4B-T x RECENT 33. |
| status flag | none (no audit flag on this row) |
| workload | S-EMBER |
| n | 845 |
| question-set hash | 6b1069d49418193d/n=845 |
| frame timestamps source | recorded per request (`frame_timestamps`) |
| input frame hashes | UNKNOWN |
| frame count | median 37, range [7, 37] |
| final processed resolution | UNKNOWN |
| vision tokens | UNKNOWN |
| total prompt tokens | median 12420, range [2437, 12536] |
| input format | separate images (llama.cpp multimodal) |
| header / template hash | UNKNOWN |
| model | 4B-I |
| snapshot | Qwen3VL-4B-Instruct-F16.gguf sha256 4a6fb1ed053e1628 |
| quantization / dtype | F16 GGUF |
| runtime + version | llama.cpp c0fd78626405 |
| attention backend | llama.cpp -fa on (flash attention) |
| host and GPU | a6000 (GPU 1) - per the StudyDevAcc-llamacpp registry row |
| batching mode | serial, one request at a time |
| concurrency | 1 |
| decoding | temperature=0.0, max_tokens=512 |
| max tokens | 512 |
| prefix-cache state | UNKNOWN |
| timing boundary | NOT VALID AS LATENCY (contended; no per-request timing recorded) |
| correctness definition | exact match of parsed letter (`correct`), parse_status recorded |
| result file | results/device/accuracy_C1.jsonl |
| accuracy_pct | 31.4793 |
| registry_hosts | a6000 (GPU 1) |

### `device.C2`

| field | value |
|---|---|
| experiment | StudyDevAcc-llamacpp |
| cell | C2 |
| status (registry) | no distinct status column in this row; verdict cell reads: **CROSSOVER REPLICATES ON THE DEVICE RUNTIME.** 845 x 4 cells complete. A: C1 4B-I x RECENT 31.5% [28.4,34.7], C2 x RICH 31.0% [28.0,34.2], C3 4B-T x RECENT 33. |
| status flag | none (no audit flag on this row) |
| workload | S-EMBER |
| n | 845 |
| question-set hash | 6b1069d49418193d/n=845 |
| frame timestamps source | recorded per request (`frame_timestamps`) |
| input frame hashes | UNKNOWN |
| frame count | median 37, range [7, 37] |
| final processed resolution | UNKNOWN |
| vision tokens | UNKNOWN |
| total prompt tokens | median 12411, range [2437, 12523] |
| input format | separate images (llama.cpp multimodal) |
| header / template hash | UNKNOWN |
| model | 4B-I |
| snapshot | Qwen3VL-4B-Instruct-F16.gguf sha256 4a6fb1ed053e1628 |
| quantization / dtype | F16 GGUF |
| runtime + version | llama.cpp c0fd78626405 |
| attention backend | llama.cpp -fa on (flash attention) |
| host and GPU | a6000 (GPU 1) - per the StudyDevAcc-llamacpp registry row |
| batching mode | serial, one request at a time |
| concurrency | 1 |
| decoding | temperature=0.0, max_tokens=512 |
| max tokens | 512 |
| prefix-cache state | UNKNOWN |
| timing boundary | NOT VALID AS LATENCY (contended; no per-request timing recorded) |
| correctness definition | exact match of parsed letter (`correct`), parse_status recorded |
| result file | results/device/accuracy_C2.jsonl |
| accuracy_pct | 31.0059 |
| registry_hosts | a6000 (GPU 1) |

### `device.C3`

| field | value |
|---|---|
| experiment | StudyDevAcc-llamacpp |
| cell | C3 |
| status (registry) | no distinct status column in this row; verdict cell reads: **CROSSOVER REPLICATES ON THE DEVICE RUNTIME.** 845 x 4 cells complete. A: C1 4B-I x RECENT 31.5% [28.4,34.7], C2 x RICH 31.0% [28.0,34.2], C3 4B-T x RECENT 33. |
| status flag | CONFOUNDED (Thinking arm; sampled temperature 1.0 vs greedy Instruct comparators) - audit 2026-11-03 |
| workload | S-EMBER |
| n | 845 |
| question-set hash | 6b1069d49418193d/n=845 |
| frame timestamps source | recorded per request (`frame_timestamps`) |
| input frame hashes | UNKNOWN |
| frame count | median 37, range [7, 37] |
| final processed resolution | UNKNOWN |
| vision tokens | UNKNOWN |
| total prompt tokens | median 12422, range [2439, 12538] |
| input format | separate images (llama.cpp multimodal) |
| header / template hash | UNKNOWN |
| model | 4B-T |
| snapshot | Qwen3VL-4B-Thinking-F16.gguf sha256 b0af534e2a0a90d5 |
| quantization / dtype | F16 GGUF |
| runtime + version | llama.cpp c0fd78626405 |
| attention backend | llama.cpp -fa on (flash attention) |
| host and GPU | a6000 (GPU 1) - per the StudyDevAcc-llamacpp registry row |
| batching mode | serial, one request at a time |
| concurrency | 1 |
| decoding | temperature=1.0, top_p=0.95, top_k=20, presence_penalty=0.0, repeat_penalty=1.0, max_tokens=16384 |
| max tokens | 16384 |
| prefix-cache state | UNKNOWN |
| timing boundary | NOT VALID AS LATENCY (contended; no per-request timing recorded) |
| correctness definition | exact match of parsed letter (`correct`), parse_status recorded |
| result file | results/device/accuracy_C3.jsonl |
| accuracy_pct | 33.3728 |
| registry_hosts | a6000 (GPU 1) |

### `device.C4`

| field | value |
|---|---|
| experiment | StudyDevAcc-llamacpp |
| cell | C4 |
| status (registry) | no distinct status column in this row; verdict cell reads: **CROSSOVER REPLICATES ON THE DEVICE RUNTIME.** 845 x 4 cells complete. A: C1 4B-I x RECENT 31.5% [28.4,34.7], C2 x RICH 31.0% [28.0,34.2], C3 4B-T x RECENT 33. |
| status flag | CONFOUNDED (Thinking arm; sampled temperature 1.0 vs greedy Instruct comparators) - audit 2026-11-03 |
| workload | S-EMBER |
| n | 845 |
| question-set hash | 6b1069d49418193d/n=845 |
| frame timestamps source | recorded per request (`frame_timestamps`) |
| input frame hashes | UNKNOWN |
| frame count | median 37, range [7, 37] |
| final processed resolution | UNKNOWN |
| vision tokens | UNKNOWN |
| total prompt tokens | median 12413, range [2439, 12525] |
| input format | separate images (llama.cpp multimodal) |
| header / template hash | UNKNOWN |
| model | 4B-T |
| snapshot | Qwen3VL-4B-Thinking-F16.gguf sha256 b0af534e2a0a90d5 |
| quantization / dtype | F16 GGUF |
| runtime + version | llama.cpp c0fd78626405 |
| attention backend | llama.cpp -fa on (flash attention) |
| host and GPU | a6000 (GPU 1) - per the StudyDevAcc-llamacpp registry row |
| batching mode | serial, one request at a time |
| concurrency | 1 |
| decoding | temperature=1.0, top_p=0.95, top_k=20, presence_penalty=0.0, repeat_penalty=1.0, max_tokens=16384 |
| max tokens | 16384 |
| prefix-cache state | UNKNOWN |
| timing boundary | NOT VALID AS LATENCY (contended; no per-request timing recorded) |
| correctness definition | exact match of parsed letter (`correct`), parse_status recorded |
| result file | results/device/accuracy_C4.jsonl |
| accuracy_pct | 30.8876 |
| registry_hosts | a6000 (GPU 1) |

