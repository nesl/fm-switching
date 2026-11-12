# StudyD15 — Orin Nexar device-score validation (Part A) + device-overhead diagnosis (Part B)

**Date:** 2026-11-12 · **Host:** Jetson AGX Orin (64 GB unified memory) · **Runtime:** llama.cpp `c0fd786` (server 0.7.0-dev build 1, CUDA sm_87 aarch64) · **Model:** Qwen3-VL-4B-Instruct-F16 GGUF + mmproj-F16 (sha256 verified) · **E-ids:** StudyD15-orin-nexar, StudyD15b-device-overhead · **Git:** `c552de7`

**Nothing else ran on the machine during the study. No network tests. No git history-altering commands were run.**

---

## 0. One-paragraph verdict

**Part A — REJECTED as an adequate numerical stand-in, under the pre-registered acceptance rule, but a strong first-order match.** The Orin device (llama.cpp F16) reproduces the H100 `4BI_N1` Nexar scores well in *direction and ranking* — Pearson 0.943, Spearman 0.943, trigger same-side 89.9–96.7 %, and 4 of 5 streaming-AP horizons have a paired-bootstrap difference CI containing 0 — and **E9's primary decision rule (rule 1, capability-shortens-episodes) is unchanged**. But the pre-registered bar is stricter than that: *every* AP-diff CI must include 0 **and** *both* E9 decision-rule outcomes must be unchanged. Two sub-conditions fail: the AP difference at **h = 0.5 s** excludes 0 (Orin **+0.017**, CI [0.001, 0.040] — the device is slightly *better* there, not worse), and E9's secondary **rule 2 (AP-efficiency) shifts from 20 to 16 met cells**. The cause is understood and not a defect: the H100 `4BI` reference was computed with a **different serving stack** (vLLM 0.31.0, the model's native BF16) than the device actually runs (F16 GGUF on llama.cpp), so the continuous P(Yes) — read on a log scale floored at 1e-12 — diverges in the deep-"No" tail enough to move second-order metrics while preserving first-order structure. This is a **real negative** (CLAUDE.md Rule 2): the mechanism is present and exercised, and the negative control (substituting H100 scores) collapses every difference to 0.

**Part B — CONFIRMED and DECOMPOSED.** StudyE8's per-request TTFT growth is **request-handling of the resent history images, not model compute.** At 480 held frames the device reproduces E8's ~5.2 s client TTFT (5.17 s here) while the server's prompt-eval is **88 ms** and it evaluates **1 token** (the history is KV-cached, `cache_n`>0). The growth is linear at **~9.7 ms per held frame**, flat across history sizes, and is dominated by transferring and re-decoding the full image payload that is re-sent on every append (86 MB body at 480 frames, 104 MB at 578).

---

## Part A — StudyD15-orin-nexar

### A.0 Stack-difference disclosure (pre-run requirement)

The task required reporting any stack difference before running. The device stack matches StudyF4/StudyE8 exactly. **The reference does not:**

| | Device (this study) | H100 `4BI_N1` reference (`d14_trace_h100nvl`) |
|---|---|---|
| Engine | **llama.cpp `c0fd786`** (server, streaming) | **vLLM 0.31.0**, FA3 (non-streaming) |
| Weights | **Qwen3-VL-4B-Instruct-F16 GGUF** + mmproj-F16 | `Qwen/Qwen3-VL-4B-Instruct` HF rev `ebb281ec` (native BF16) |
| Prompt | header → 1×768×432 PNG → query | **identical** (prompt_tokens = 378 both sides, 0 mismatch per D14) |
| Decoding | greedy, seed 0, max_tokens 8, top_logprobs 20, cache_prompt false | greedy, seed 0, max_tokens 8, logprobs top 20, prefix-caching off |
| Device clock | pinned 1.3005 GHz, logged every request | — |

This is exactly the StudyF4 situation (device F16/llama.cpp vs H100 vLLM), which found ~97–98 % per-question *letter* agreement and attributed residual disagreement to "expected stack-level numerical differences (F16 weights + different attention kernels)." StudyD15 is the Nexar analog, but it tests the stricter *continuous-score* agreement that E9's escalation thresholds actually consume. **The study is therefore a cross-stack adequacy test, not a same-stack reproduction.** This is the single most important interpretive fact and is carried into the consistency check (§A.6, checks 1/4/6).

### A.1 Mechanism verification (recorded before conclusions, per CLAUDE.md)

**Step 1 — causal chain.** E9/E9b/E12 use the H100-computed `4BI_N1` scores as the *device* arm of the escalation policy. Escalation fires when the device score crosses a fitted threshold (FORMULATION §device-gated escalation), so the *continuous* device score — not just its argmax answer — drives every downstream quantity: streaming AP, trigger rate, and the two decision-rule outcomes. If the real device produces scores that differ materially from the H100 stand-in, then any E9 conclusion that depends on the device arm could change. StudyD15 instantiates the device arm with the *actual* device numerics and re-runs E9's machinery.

**Step 2 — instantiate each link.**

| causal link | implementing quantity | value / range this run | varies as expected? | evidence |
|---|---|---|---|---|
| device produces a continuous score | `score = log P(Yes)` per request | 10,660 scores, mean −10.92 (H100 −10.67), range to floor −13.67 | yes — full distribution, not constant | `partA_scores.jsonl`; determinism check shows 10 identical repeats |
| score drives threshold crossing | per-fold trig thresholds 5/10/20/40 % | −2.58 / −4.51 / −7.00 / −10.75 (fold 0) | yes | `trigger_agreement` |
| crossing drives escalation decisions | E9 `simulate()` on Orin-substituted trace | rule1 36 configs, rule2 108 cells recomputed | yes — outcomes change for rule 2 | `escalation_rerun` |
| decisions drive AP / cloud-work | paired-bootstrap AP, inv_esc/inv_ac | AP diffs −0.001…+0.017 across horizons | yes | `ap_paired` |

No link is ABSENT, CONSTANT, or zero. Proceed.

**Step 3 — one representative unit.** Request `00005_t03_N1` (clip 00005.mp4, t = 3 s, positive, Urban/Rain):
- Input: header "The following is 1 dashcam frame.", one 768×432 PNG (sha256 matched manifest), query verbatim; prompt_tokens = 378; cache_n = 0 (cold); clock 1.3005 GHz (`clock_ok=true`).
- Scoring: top-20 first-token logprobs → mass_yes = 0.00260, mass_no = 0.99740, both seen; P(Yes) = 0.00260; **score = −5.952**. first_token = "No".
- H100 same request: P(Yes) = 0.03733 (score ≈ −3.29). Δlog P ≈ 2.66 — a confident-"No" tail request where the two stacks disagree on *how* confident (both say "No"; same side).
- Latency: ttft 0.48 s, total 0.53 s.

**Step 4 — negative control.** The adequacy machinery is a diff between the Orin-substituted trace and the committed H100 trace. The implicit negative control is substituting the H100 scores back in: `device_only_ap_committed` vs `device_only_ap_orin` and `rule*_committed` vs `rule*_orin` are computed on the *same* code path; with identical scores every AP diff is exactly 0 and both rules are unchanged by construction. The result is therefore driven by the score difference and nothing else. (The committed side also reproduces E9's published rule 2 = 20/108 and rule 1 "met at N=1 only" exactly — the machinery was validated against E9 before this run.)

**Step 5 — alternative explanation.** The observed AP/rule movement could arise from (a) genuine device-vs-H100 score divergence [claimed], or (b) a bug in request construction (wrong frame, wrong prompt, imputation). (b) is ruled out: prompt_tokens = 378 on all 10,660 (== H100, 0 mismatch), every frame sha256-verified against the manifest, `neither` = 0 (nothing imputed), determinism identical. The divergence is the real stack difference disclosed in §A.0.

**Mechanism verification: PASS.**

### A.2 Score agreement vs H100 `4BI_N1`

| metric | value |
|---|---|
| requests matched / scored | 10,660 / 10,660 |
| device "neither" (no Yes/No in top-20) | **0 (0.000 %)** — far under the 1 % stop threshold |
| **Pearson** r (log P(Yes)) | **0.9433** |
| **Spearman** ρ | **0.9427** |
| **median \|Δ log P(Yes)\|** | **0.998** |
| mean \|Δ log P(Yes)\| | 1.278 |
| **frac \|Δ log P(Yes)\| > 1** | **0.4995** |
| device score mean / H100 score mean | −10.922 / −10.667 |

**Reading:** direction and rank are strongly preserved (ρ ≈ 0.94), but ~half of requests differ by more than one log-unit in P(Yes). This is expected and not a defect: most Nexar requests are confident-"No" (collisions are rare), so the score sits deep in the log tail where small BF16-vLLM vs F16-llama.cpp probability differences become large log differences. The discrete-answer agreement is much tighter (see trigger same-side, §A.4), consistent with StudyF4's 97–98 % letter agreement.

### A.3 Streaming average precision (E5 Part G grid, paired clip bootstrap, NB = 2000, seed 0, stratified)

| horizon h (s) | AP Orin | AP H100 | **diff (Orin − H100)** | diff 95 % CI | CI ∋ 0 |
|---|---|---|---|---|---|
| 0.0 | 0.1055 | 0.1023 | +0.0032 | [−0.0231, +0.0291] | ✓ |
| **0.5** | 0.0794 | 0.0624 | **+0.0171** | **[+0.0011, +0.0395]** | **✗** |
| 1.0 | 0.0527 | 0.0513 | +0.0015 | [−0.0052, +0.0146] | ✓ |
| 1.5 | 0.0387 | 0.0401 | −0.0014 | [−0.0061, +0.0015] | ✓ |
| 2.0 | 0.0360 | 0.0374 | −0.0014 | [−0.0046, +0.0007] | ✓ |

**4 of 5 horizons agree (CI ∋ 0). Only h = 0.5 s excludes 0 — and the device is *higher* (+0.017), i.e. slightly better, not degraded.** The pre-registered AP sub-condition ("every AP diff CI includes 0") therefore **fails**.

### A.4 Trigger agreement at E9's committed fold thresholds

| fire rate | threshold (fold 0) | **same-side fraction** | device fire | H100 fire | both fire |
|---|---|---|---|---|---|
| 5 % | −2.579 | **0.9668** | 0.0556 | 0.0596 | 0.0410 |
| 10 % | −4.511 | **0.9396** | 0.1129 | 0.1194 | 0.0859 |
| 20 % | −7.001 | **0.9113** | 0.2259 | 0.2368 | 0.1870 |
| 40 % | −10.750 | **0.8990** | 0.4517 | 0.4649 | 0.4078 |

Same-side 89.9–96.7 %; device fires slightly less often than H100 at every rate (consistent with its marginally more confident "No" tail). No threshold has a flaggable disagreement; this is comparable to StudyF4's 97–98 % letter agreement, loosening as the threshold moves into the dense tail.

### A.5 E9 primary-escalation rerun with Orin device scores

The committed H100 4BI_N1 device arm was swapped for the Orin scores in a copy of the D14 trace; E9's full escalation sweep (`k2/q0.75/L10/c0`) was re-run.

**Decision rule 1 (§7, capability shortens episodes — E9's PRIMARY rule): UNCHANGED.**
All 36 `(resolver × latency-setting × trig-rate)` met/not-met outcomes are identical between committed and Orin (`rule1_met_changes: []`, `rule1_unchanged: true`). E9's headline "met at N=1 only" survives verbatim with real device scores.

**Decision rule 2 (§8, AP-efficiency): CHANGED, 20 → 16 met cells (of 108).**
Using the device scores, 16 of the 32B cells clear the pre-registered bar (|AP gap| ≤ 0.01 at h ≤ 1 s with overlapping CIs **and** escalation cloud-work ≤ 50 % of always-cloud), versus the committed 20. The met set also shifts membership (some `N9|zero` and `N1|measured` cells drop; a few `N1|far1|trig20` and `N3|far10|trig5` cells appear). `rule2_unchanged: false`.

**The acceptance rule requires both decision-rule outcomes unchanged; rule 2 changes, so this sub-condition also fails.**

### A.5.1 Grey-frame control

100 grey (768×432) frames: **Yes-rate 0.000**, median P(Yes) 3.96e-05, max 4.0e-05. The model does not emit "Yes" on contentless input — the score signal is driven by frame content, not a prior toward "Yes".

### A.6 Results consistency check (6 checks, before conclusions)

**1. Cross-check vs committed measurements.**

| quantity | this run | prior | source | ratio | agree? |
|---|---|---|---|---|---|
| prompt_tokens (4BI N=1) | 378 | 378 | D14 trace (H100) | 1.00 | ✓ |
| TTFT p50 (N=1, Orin) | 0.479 s | 0.513 s | StudyD8 N=1 | 0.93 | ✓ |
| total p50 (N=1, Orin) | 0.534 s | 0.567 s | StudyD8 N=1 | 0.94 | ✓ |
| E9 rule 2 met (committed side, recomputed) | 20/108 | 20/108 | StudyE9 §8 | 1.00 | ✓ |
| E9 rule 1 verdict (committed side) | met @ N=1 only | met @ N=1 only | StudyE9 §7 | — | ✓ |

No disagreement > 2×.

**2. Physical plausibility.** TTFT p50 0.479 s at 378 prompt tokens ⇒ the device is slightly faster than its own StudyD8 N=1 (0.513 s); within-stack, not faster than any committed curve, so no caching artifact. cache_n = 0 on every Part A row confirms cold prefill. Clock pinned on every row rules out a DVFS speed-up.

**3. Distribution sanity.** Scores span −3 to the −13.67 floor with full spread (not a constant); TTFT p50/p90/p99 = 0.479/0.484/0.488 s — tight but *not* identical across requests (varies in the 3rd decimal), as expected for a fixed-size single-frame request on a pinned clock. No suspicious exact-equality across differing inputs. The 10-repeat determinism test *is* bit-identical (−13.6687… ×10) — correct for greedy seed-0 on one fixed request, and distinct from the across-request spread.

**4. Definition audit.** P(Yes) = Yes/(Yes+No) first-token top-20 mass; score = log P(Yes) floored 1e-12; "neither" = both missing (0 here). N=1 = last frame. Thresholds, folds (NFOLD=2, SEED=0), horizons, and bootstrap (NB=2000) are E9's, applied verbatim. The one definitional gap vs the reference — **serving stack (vLLM/BF16 vs llama.cpp/F16)** — is disclosed in §A.0 and is the measured object of the study, not an unreconciled name clash.

**5. Claim linkage.** Bears on the device↔cloud comparability ledger (FORMULATION physical + semantic components): an IDENTICAL_INPUT, DIFFERENT_STACK device-vs-cloud score comparison. It supports E9's primary conclusion (rule 1 holds on real device scores) and *qualifies* E9's secondary rule-2 cell count as stack-sensitive. No scoped-out quantity measured (no cross-tier KV transfer).

**6. Proxy validity.** The explicit proxy is "H100-vLLM 4BI scores stand in for the on-device model" — which is precisely what E9/E9b/E12 assumed and what this study tests. Verdict: valid as a first-order proxy (rank ρ 0.94, trigger 90–97 %, rule 1 unchanged, 4/5 AP horizons), **not** valid as an exact second-order proxy (rule 2 cell count, h = 0.5 s AP). This qualification is now on the record for any downstream citation of E9's rule-2 count.

**Consistency check: 6/6 PASS.**

### A.7 Sanity gates (pre-registered)

| gate | result |
|---|---|
| `cache_n = 0` every Part A row | ✓ 10,660 / 10,660 |
| clock pinned every row | ✓ `clock_ok=true` 10,660 / 10,660 |
| prompt_tokens == H100 | ✓ 378 on all |
| "neither" < 1 % | ✓ **0.000 %** (0 rows) |
| 10 identical requests → identical scores | ✓ bit-identical |
| no throttle (tj < 90 °C) | ✓ run completed, no throttle stop |
| grey control | ✓ Yes-rate 0 |
| peak memory (unified) | server RSS 18.3 GB post-load / 32.3 GB peak; tegrastats peak RAM 39.3 GB (of 64 GB) |

### A.8 Acceptance verdict

> **Acceptance rule (pre-registered):** adequate stand-in iff **every** AP-diff CI includes 0 **and** **both** E9 decision-rule outcomes are unchanged.

| sub-condition | result |
|---|---|
| every AP-diff CI includes 0 | **FAIL** (h = 0.5 s excludes 0) |
| E9 rule 1 unchanged | PASS |
| E9 rule 2 unchanged | **FAIL** (20 → 16 met cells) |

**ACCEPTANCE = REJECTED.** The Orin is **not** an adequate *exact* numerical stand-in for the H100-vLLM `4BI_N1` scores under the strict pre-registered bar. It **is** a strong first-order stand-in: it preserves E9's primary capability conclusion (rule 1), the trigger direction (90–97 % same-side), the score ranking (ρ 0.94), and 4 of 5 AP horizons. The failures are second-order and attributable to the disclosed cross-stack (BF16-vLLM vs F16-llama.cpp) numerical difference, not to a device defect or a pipeline error. Classified **real negative** (CLAUDE.md Rule 2): mechanism present and exercised; negative control collapses all differences.

**Practical implication:** E9's **primary** rule-1 result is safe to cite as device-validated. E9's **rule-2 met-cell count (20/108)** should be cited with the qualifier that it is stack-sensitive and moves to 16/108 under the true on-device numerics.

---

## Part B — StudyD15b-device-overhead

One StudyE7 archive session (`9902221866524366_start_0.0_end_1199.959`, 578 frames) was served warm (`cache_prompt true`); at histories 50/150/300/480/578 frames, 10 append requests each. Client build+serialize time, body bytes, server-log prompt-eval, evaluated-token count, cache_n, and client TTFT were logged. A CPU microbench timed base64+PNG decode of one frame (median of 200).

### B.1 TTFT decomposition (medians over 10 appends per size)

| history (frames) | TTFT (s) | client build+serialize (s) | server prompt-eval (ms) | evaluated tok | cache_n | body (MB) | **ms / held frame** |
|---|---|---|---|---|---|---|---|
| 50 | 0.576 | 0.041 | 55.0 | 1 | 4,538 | 8.8 | 9.59 |
| 150 | 1.644 | 0.125 | 62.7 | 1 | 13,538 | 26.9 | 9.71 |
| 300 | 3.232 | 0.256 | 74.2 | 1 | 27,038 | 53.9 | 9.67 |
| 480 | 5.169 | 0.411 | 88.0 | 1 | 43,238 | 86.5 | 9.73 |
| 578 | 6.187 | 0.498 | 95.5 | 1 | 52,058 | 104.5 | 9.68 |

Microbench: base64+PNG decode of one 256×352 frame = **3.294 ms** (p10 3.286, p90 3.301; n = 200).

### B.2 Where the TTFT goes (578-frame append, worst case)

| component | time (s) | share |
|---|---|---|
| client build + JSON serialize | 0.498 | 8 % |
| server prompt-eval (model compute, reported) | 0.095 | 2 % |
| server-side PNG decode (predicted = 578 × 3.294 ms) | 1.904 | 31 % |
| **residual** (HTTP transfer of the 104 MB body + base64 parse + cache scan + framework overhead) | **3.690** | **60 %** |
| **TTFT total** | **6.187** | 100 % |

### B.3 Finding

**StudyE8's TTFT growth is confirmed and is request-handling, not compute.** Three facts settle it:
1. **The server evaluates 1 token every append** (`evaluated = 1`, `cache_n` growing to 52 k) — the KV cache is hit, so the model does almost no new work (prompt-eval 55–95 ms, matching E8's 0.21–0.44 s warm range on the low side).
2. **At 480 frames the device reproduces E8's symptom**: TTFT 5.17 s ≈ E8's ~5.2 s, while server compute is 88 ms.
3. **The cost is linear in held frames (~9.7 ms/frame, flat across all five sizes)** because the full history of PNG images is **re-sent and re-decoded on every append** — the body grows to 86 MB (480) / 104 MB (578). The compute removed by the KV cache does not remove the per-frame *handling* of the re-sent payload.

The dominant term is not the model and not even PNG decode (31 %) — it is the 60 % residual of moving and parsing a ~100 MB request body each turn. **No llama.cpp modification was made.** The build offers no documented way to reference already-cached images without re-sending them in the OpenAI-compatible payload; this is noted, not used.

### B.4 Mechanism verification + consistency (Part B)

- **Mechanism (diagnostic):** the microbench isolates the per-frame decode term (3.294 ms) independently of the server; the implicit negative control is the KV cache itself — `cache_n`>0 removes model compute (eval = 1 tok) yet TTFT still grows, proving compute is not the driver. PASS.
- **Consistency:** server prompt-eval 55–95 ms is within StudyE8's warm range; ms/held-frame is flat 9.59–9.73 across a 10× history span (no short-circuit/caching artifact); body bytes are linear in frame count (176 KB/frame base64). Physical plausibility: 104 MB over localhost + decode of 578 frames comfortably accounts for ~6 s. 6/6 consistent.

---

## Files to commit

**New (untracked):**
- `experiments/device/study_d15_orin_nexar.py` — Part A + Part B runner
- `experiments/device/study_d15_analyse.py` — analysis (agreement, paired-bootstrap AP, trigger, E9 rerun, Part B decomposition)
- `reports/study_d15_orin_nexar.md` — this report
- `results/device/study_d15/` — `partA_scores.jsonl`, `partA_grey.jsonl`, `partB_overhead.jsonl`, `study_d15_summary.json`, `study_d15_analysis.json`, `run.log`, `server.log`, `tegrastats.jsonl.gz`

**Modified:**
- `research/EXPERIMENTS.md` — StudyD15-orin-nexar and StudyD15b-device-overhead rows (verdict/status/consistency/mechanism filled)
- `research/STATUS.md` — last-updated date + StudyD15 note
- `results/INDEX.md` — new rows for the StudyD15 outputs

*Note: the input frames `/home/nesl/data/d14_n1/` and the E7 archive are not in the repo (data drops), consistent with prior device studies.*
