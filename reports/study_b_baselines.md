# StudyB-baselines: the baseline suite for the scheduler evaluation

E-id: StudyB-baselines (`research/EXPERIMENTS.md`). **This is an engineering and literature task. It runs no experiment and makes no performance claim, and no two baselines are compared anywhere in it.** CPU only on the flash host: no GPU, no model server, no inference. The network was used only to search for papers, clone public repositories and pip-install into a throwaway venv; third-party code lives **outside this repository** in `~/baselines_src/` and is never vendored into it.

## 0. Three things to read before the tables

**(a) StudyE10e does not exist.** The tuned-engine baseline was specified as "the best engine configuration from StudyE10c / E10e (priority + step budget + long-prefill threshold)". There is no `reports/study_e10e*.md` and no StudyE10e row in the registry (only E10a, E10b, E10c, E10d). Worse for the specification: **StudyE10c's verdict is that no engine setting helps** - E0 (default), E1 (priority), E2 (2,048-token step budget) and E4 (both) were "identical to E0 in 12 / 12 comparable ladders" - and **the long-prefill threshold was never run** (StudyE10d lists it as an untested lever). So the best *measured* configuration is the default. `tuned_engine.py` therefore exposes only the four configurations a committed study measured, defaults to E0 with the reason attached, and **raises** if asked for any other name, so no table downstream can contain a number no measurement supports. **This needs your decision** (see §7).

**(b) Ekya's repository has no licence.** `github.com/edge-video-services/ekya` is Microsoft Research's own release, but it contains **no LICENSE or COPYING file anywhere** and the README names none, so no right to use or modify is granted. Applied consequence: the clone is used for citation and commit pinning only, **no file in it was opened, run or copied**, its own CPU-runnable toy simulator was deliberately left unrun, and the adapted baseline was written from the paper. Flagged rather than resolved.

**(c) StudyRH8's winning policy reads labels.** RH8's MIX-DEMAND keeps warm "exactly the high-demand devices" - in the code, the same `random.Random(0).sample(...)` draw that *assigned* the synthetic demand. RH8's own 2026-11-03 audit says this "does not show that demand can be *predicted*". Our interface forbids a policy from reading labels, so rather than invent a hybrid, **both readings ship and are labelled**: `RH8OracleDemand` (an upper bound, excluded from the causality check, reported like the hindsight oracle) and `RH8CausalDemand` (deployable, but **not** what StudyRH8 measured).

## 1. The policy interface

Defined first, in `experiments/orchestration/baselines/interface.py`, before any baseline. It is enforced, not merely documented:

- **Causal observations only.** `Observation` is frozen and the fields that could leak the future are absent; `scrub()` additionally asserts that no field or dict key named in `FORBIDDEN_FIELDS` (17 of them: labels, correctness, `time_of_event`, future arrivals, oracle values, ...) reached the policy. It runs on **every** epoch via `Policy.__call__`.
- **One action space.** `validate_action` rejects a cadence outside {0.25, 0.5, 1.0} s, a frame count outside {1, 3}, an unknown representation or session action, a negative defer, or an action naming an entity the observation did not contain - which is how a policy would smuggle in knowledge of the future.
- **One set of defaults.** A baseline that decides only part of the space leaves the rest `None` and `apply_defaults` fills it from `DEFAULTS`, *identically for every baseline*: cloud N = 1 at c = 0.5 s, recall on cloud with RECENT, LRU host offload, FCFS order, default engine. Each card lists which defaults its baseline relies on.
- **One budget.** `Budget` is checked by the harness, not the policy, so no baseline can award itself more cloud work than our scheduler gets.

Supporting modules, all reading committed measurements and nothing else: `costs.py` (StudyD4 / D7 / D7b / D8 / RH5 / E10b / E10d constants, re-exported from `study_e9_episodes.py` so there is one copy per constant in the repo), `profiles.py` (the resource-quality profile from StudyE9b / E9c), `devsplit.py` (**StudyD3's development clips** - the only place a hyperparameter may be fitted; StudyD14 / D14b are the validation clips and are never fitted on).

One interpolation rule is stated rather than measured: `costs.recall_ttft_s` interpolates linearly in tokens between StudyRH5's 11k and 28k points for the warm states and uses the measured cold prefill rate for COLD. Every card that relies on it says so.

## 2. The four cases, as decided

"Code exists" means an official or author-endorsed public repository. A third-party reimplementation counts only if the paper's authors link it; otherwise it is treated as no code and the search is recorded.

| case | meaning | count |
|---|---|---|
| **A** | code exists and runs in our setting; wrapped, decision logic untouched | 1 |
| **B** | code exists but needs adaptation; ORIGINAL (pinned) + ADAPTED both kept | 8 |
| **C** | no code; faithful reconstruction, usable unchanged | 0 |
| **D** | no code and needs adaptation; reconstruction + adapted both kept | 13 |
| naive | implemented directly behind the interface | 7 |
| own | our own measured configuration, not an external paper | 1 |

No candidate came out as case C: every paper without code also needed adaptation, because our action space (two tiers, three representations, a standing video query plus a stateful recall session) differs from every paper's.

## 3. Naive baselines

| name | what it decides | file |
|---|---|---|
| `device-only` | episodic mode, recall decision | `naive.py::DeviceOnly` |
| `always-cloud-fcfs` | episodic mode, recall decision (vLLM default) | `naive.py::AlwaysCloudFCFS` |
| `random-admission` | episodic mode, recall decision; 20 seeds | `naive.py::RandomAdmission` |
| `round-robin` | equal cloud share per stream | `naive.py::RoundRobin` |
| `static-partition` | fixed cloud share per query class | `naive.py::StaticPartition` |
| `edf-service-time` | recall admission by service-time estimate, EDF order | `naive.py::EDFServiceTime` |
| `hindsight-oracle` | everything; UPPER BOUND, reads the future | `naive.py::HindsightOracle` |

`hindsight-oracle` is an **upper bound, not a policy**: the interface forbids future information in the observation, so the harness injects the realised trace through the constructor, the class declares `reads_future = True`, and the causality check excludes it. The same mechanism carries `RH8OracleDemand`.

## 4. Shortlist: case decision, evidence, versions built

| baseline | paper (verified) | code | case | versions | card |
|---|---|---|---|---|---|
| `videostorm` | Zhang et al., Live Video Analytics at Scale with Approximation and Delay-Tolerance, NSDI 2017<br>*OpenAlex: NSDI 2017* | none found | **D** | reconstruction, adapted | `cards/videostorm.md` |
| `ekya` | Bhardwaj et al., Ekya, NSDI 2022<br>*OpenAlex: arXiv 2020 record; USENIX NSDI 2022 page* | `https://github.com/edge-video-services/ekya`<br>@`2a6c8201db95` | **B** | original (cloned, NOT executed), adapted | `cards/ekya.md` |
| `tuned-engine` | -<br>*n/a* | ours (StudyE10c) | **own** | adapted | `cards/tuned_engine.md` |
| `clockwork` | Gujarati et al., Serving DNNs like Clockwork, OSDI 2020<br>*OpenAlex: arXiv 2020 record; USENIX OSDI 2020 page* | `https://gitlab.mpi-sws.org/cld/ml/clockwork`<br>@`6ce83e029051` | **B** | original (cloned, not built), adapted | `cards/clockwork.md` |
| `confidence-cascade` | Chen et al., FrugalGPT, TMLR 2024; Aggarwal et al., AutoMix, NeurIPS 2024<br>*OpenAlex: FrugalGPT arXiv 2023 record; AutoMix NeurIPS 2024* | `https://github.com/stanford-futuredata/FrugalGPT` +1<br>@`frugalgpt 2b` | **B** | original (cloned), adapted | `cards/cascade.md` |
| `inar-vl` | Sabanovic, Maliakel, Brandic, INAR-VL, arXiv:2605.18853 (EdgeSys 2026)<br>*arXiv abstract page* | none found | **D** | reconstruction, adapted | `cards/inarvl.md` |
| `hybrid-llm` | Ding et al., Hybrid LLM, ICLR 2024<br>*OpenAlex: arXiv 2024 record; ICLR 2024 proceedings page* | none found | **D** | reconstruction, adapted | `cards/hybrid_llm.md` |
| `routellm` | Ong et al., RouteLLM, arXiv:2406.18665<br>*OpenAlex: arXiv 2024 record* | `https://github.com/lm-sys/RouteLLM`<br>@`0b64fdafe049` | **B** | original (cloned), adapted | `cards/routellm.md` |
| `perllm` | Yang et al., PerLLM, arXiv:2405.14636<br>*OpenAlex: arXiv 2024 record* | none found | **D** | reconstruction, adapted | `cards/perllm.md` |
| `attentionstore` | Gao et al., CachedAttention / AttentionStore, USENIX ATC 2024 (arXiv:2403.19708)<br>*OpenAlex: arXiv 2024 record; USENIX ATC 2024 page* | none found | **D** | reconstruction, adapted | `cards/attentionstore.md` |
| `lmcache` | LMCache (system paper arXiv:2510.09665)<br>*repository + arXiv id* | `https://github.com/LMCache/LMCache`<br>@`6d8376b1248c` | **B** | original (cloned), adapted | `cards/lmcache.md` |
| `pensieve` | Yu, Lin, Li, Pensieve, EuroSys 2025 (arXiv:2312.05516)<br>*OpenAlex: EuroSys 2025* | none found | **D** | reconstruction, adapted | `cards/pensieve.md` |
| `rh8-demand-aware` | StudyRH8 (ours)<br>*our own report* | experiments/cost/study_rh8_demand_aware.py | **A** | ORACLE (upper bound), causal (deployable) | `cards/rh8.md` |
| `r3-streaming` | Liu et al., R3-Streaming, arXiv:2605.17921<br>*arXiv abstract page* | none found | **D** | reconstruction, adapted | `cards/r3streaming.md` |
| `eco-llm` | Patidar, Crown, Hsieh, Xu, ECO-LLM: Orchestration for Domain-specific Edge-Cloud Language Models, arXiv:2507.09003 (11 Jul 2025, Microsoft Research)<br>*arXiv API: id, title, authors, date. NAME NOTE: a DIFFERENT 2024 paper also uses the ECO-LLM name; the id resolves to the MSR one* | none found | **D** | reconstruction, adapted | `cards/ecollm.md` |
| `streamscout` | StreamScout: Learning When to Look Deeper for Streaming Video Understanding, arXiv:2609.00291<br>*arXiv API (id found by title search; the addendum gave none)* | none found | **D** | reconstruction, adapted | `cards/streamscout.md` |
| `preble` | Srivatsa, He, Abhyankar, Li et al., Preble: Efficient Distributed Prompt Scheduling for LLM Serving, arXiv:2407.00023<br>*OpenAlex + arXiv API* | `https://github.com/WukLab/preble`<br>@`1a35eae20c41` | **B** | original (cloned), adapted | `cards/preble.md` |
| `mooncake` | Qin et al., Mooncake: A KVCache-centric Disaggregated Architecture for LLM Serving, ACM Transactions on Storage 2025 / FAST 25 (arXiv:2407.00079)<br>*OpenAlex: ACM Transactions on Storage 2025* | `https://github.com/kvcache-ai/Mooncake`<br>@`5ffbf763368d` | **B** | original (cloned), adapted | `cards/mooncake.md` |
| `kvflow` | Pan et al., KVFlow: Efficient Prefix Caching for Accelerating LLM-Based Multi-Agent Workflows, arXiv:2507.07400<br>*arXiv API verifies the id; the NeurIPS 2025 venue the addendum gives is **UNVERIFIED*** | none found | **D** | reconstruction, adapted | `cards/kvflow.md` |
| `uniscale` | Huang et al., UniScale: Adaptive Unified Inference Scaling via Online Joint Optimization of Model Routing and Test-Time Scaling, arXiv:2605.30898<br>*arXiv API verifies the id; the ICML 2026 venue the addendum gives is **UNVERIFIED*** | none found | **D** | reconstruction, adapted | `cards/uniscale.md` |
| `thinking-qwenvl-atdm` | Zhang et al., Progressive Online Video Understanding with Evidence-Aligned Timing and Transparent Decisions, arXiv:2604.18459<br>*arXiv API verifies the id; the ICLR 2026 venue the addendum gives is **UNVERIFIED*** | none found | **D** | reconstruction, adapted | `cards/thinking_qwenvl.md` |
| `simplestream` | Shen, Tian, Yang, Liu, A Simple Baseline for Streaming Video Understanding, arXiv:2604.02317<br>*arXiv API* | `https://github.com/EvolvingLMMs-Lab/SimpleStream`<br>@`be227ee8ce90` | **B** | original (cloned, NOT executed), adapted | `cards/simplestream.md` |
| `covstream` | Liu, Chen, Yan, Wu, Wang, CoVStream: Edge-Cloud Collaboration for Understanding of Long Video Streams, arXiv:2606.22804<br>*arXiv abstract page* | none found | **D** | reconstruction, adapted | `cards/covstream.md` |

### Searches that found no code

For every case-D baseline the search was: the arXiv abstract page and its "Code, Data and Media" section; the authors' institutional and personal pages; a GitHub search by paper title and by author; and, where one exists, the publisher's project page (Microsoft Research for VideoStorm and Hybrid LLM, the USENIX page for CachedAttention, the EuroSys record for Pensieve). None links an official or author-endorsed repository. VideoStorm additionally has no third-party reimplementation that the authors link.

### Reconstruction toy tests

Each case-D reconstruction runs in **the paper's own abstract setting** and each check names the qualitative behaviour it reproduces.

| reconstruction | behaviours reproduced | named from the paper |
|---|---|---|
| `reconstructed/videostorm.py` | **6/6 behaviours (Eq. 1, 2, 3, 4, S6.2.2, S6.3)** | Eq. (2) lag accumulation; S6.1/Fig. 6 one-sided lag penalty; S6.2.2/S8.2.1 MaxMin beats an equal split on the minimum; Eq. (3) vs Eq. (4) each wins on its own objective; Eq. (3)'s capacity constraint; S6.3 score range |
| `reconstructed/hybrid_llm.py` | **6/6 behaviours (S3, S3.1-3.3, Eq. 1-4)** | S3 quality gap; S3.1 vs S3.2 y^det has higher variance than y^prob; S3.3/Eq. (3) the transformation spreads labels; S3 p_w tracks Pr[H >= 0]; S4 the threshold is the cost knob; Eq. (1)/(2)/(4) BCE |
| `reconstructed/perllm.py` | **7/7 behaviours (S3.2, Eq. 4, CS-UCB, Algorithm 1)** | S3.2 f(y) >= 0 iff feasible; Eq. (4) violations penalised and energy costs; CS-UCB optimism and bonus decay; Algorithm 1 accept-first-feasible and regret update; CMAB learning |
| `reconstructed/attentionstore.py` | **6/6 behaviours (S4.1 Figs 6-7, S4.2, S4.3)** | S4.1/Fig. 6c load hidden behind compute; S4.1/Fig. 7a->7b a larger buffer reduces exposed load; S4.1 async save; S4.2 fetch follows the scheduler queue; **S4.2 eviction differs from LRU**; S4.3 decoupling survives a prefix shift |
| `reconstructed/pensieve.py` | **6/6 behaviours (S4 value ordering, token granularity, AOT swap)** | S4 value grows with recompute cost and with the reuse horizon; eviction fits the tier; token granularity gives partial residency; dropping costs more than swapping; AOT pipelined swap |
| `reconstructed/inarvl.py` | **-** | S3 stage (3) the 10-dimensional descriptor; stage (4) stronger model predicts more quality and dominated candidates are pruned; stage (5) easy stays on the edge, hard offloads, and the same input stays local when latency is priced high |
| `reconstructed/r3streaming.py` | **-** | S4.2/Fig. 2 nearby 1.0 vs historical 0.01 and the 95-96 % token reduction; the asymmetric schedule beats its inverse on nearby tokens; S4(ii) defers on weak evidence; S4(iii) escalates only the hardest within budget and nothing at budget 0; Respond gates Reason |

## 5. Smoke tests

### 5.1 Every adapted baseline: the 10-minute replay

4 episodic streams (StudyD14b traces, cloud latency from StudyE9b setting (ii) at 25 % load, device at its 0.75 s saturated cadence with 0.567 s latency) and 2 recall sessions (StudyRH4 / RH5 D2 sizes 11,050 and 28,114 tokens, costs from StudyRH5 / StudyE10b), 600 s at a 0.25-s grid = 2,401 decision epochs, one shared budget of 120 GPU-seconds, one connectivity change at t = 300 s. It checks only that the policy **runs**, **respects the interface**, **stays in budget** and **never sees a forbidden field or future data**. **No performance claim; no comparison between baselines.** The GPU-seconds and recall columns are descriptive only - they show the policy did something, not that it did well, and a lower or higher number is neither better nor worse here.

| baseline | epochs | ran | interface | budget | GPU-s spent (of 120) | recall cloud/device/deferred | reads future |
|---|---|---|---|---|---|---|---|
| `device-only` | 2401 | PASS | PASS | PASS | 0.0 | 0/40/0 | no |
| `always-cloud-fcfs` | 2401 | PASS | PASS | PASS | 119.967 | 12/28/0 | no |
| `random-admission` | 2401 | PASS | PASS | PASS | 119.981 | 10/30/0 | no |
| `round-robin` | 2401 | PASS | PASS | PASS | 119.986 | 24/16/0 | no |
| `static-partition` | 2401 | PASS | PASS | PASS | 119.967 | 12/28/0 | no |
| `edf-service-time` | 2401 | PASS | PASS | PASS | 119.967 | 12/28/0 | no |
| `hindsight-oracle` | 2401 | PASS | PASS | PASS | 119.967 | 12/28/0 | YES (upper bound) |
| `videostorm/maxmin` | 2401 | PASS | PASS | PASS | 29.313 | 40/0/0 | no |
| `videostorm/maxsum` | 2401 | PASS | PASS | PASS | 29.313 | 40/0/0 | no |
| `ekya` | 2401 | PASS | PASS | PASS | 117.739 | 8/32/0 | no |
| `tuned-engine` | 2401 | PASS | PASS | PASS | 119.967 | 12/28/0 | no |
| `clockwork` | 2401 | PASS | PASS | PASS | 119.967 | 12/28/0 | no |
| `confidence-cascade` | 2401 | PASS | PASS | PASS | 98.752 | 0/40/0 | no |
| `inar-vl` | 2401 | PASS | PASS | PASS | 119.957 | 6/34/0 | no |
| `hybrid-llm` | 2401 | PASS | PASS | PASS | 29.313 | 40/0/0 | no |
| `routellm` | 2401 | PASS | PASS | PASS | 119.967 | 12/28/0 | no |
| `perllm` | 2401 | PASS | PASS | PASS | 31.164 | 40/0/0 | no |
| `attentionstore` | 2401 | PASS | PASS | PASS | 119.988 | 12/28/0 | no |
| `lmcache` | 2401 | PASS | PASS | PASS | 119.986 | 12/28/0 | no |
| `pensieve` | 2401 | PASS | PASS | PASS | 119.967 | 12/28/0 | no |
| `rh8-demand-aware-causal` | 2401 | PASS | PASS | PASS | 119.967 | 12/28/0 | no |
| `rh8-demand-aware-ORACLE` | 2401 | PASS | PASS | PASS | 119.968 | 12/28/0 | YES (upper bound) |
| `r3-streaming` | 2401 | PASS | PASS | PASS | 74.149 | 0/40/0 | no |
| `eco-llm` | 2401 | PASS | PASS | PASS | 119.711 | 10/30/0 | no |
| `streamscout` | 2401 | PASS | PASS | PASS | 0.0 | 0/40/0 | no |
| `preble` | 2401 | PASS | PASS | PASS | 119.999 | 12/28/0 | no |
| `mooncake` | 2401 | PASS | PASS | PASS | 119.999 | 12/28/0 | no |
| `kvflow` | 2401 | PASS | PASS | PASS | 119.991 | 12/28/0 | no |
| `uniscale` | 2401 | PASS | PASS | PASS | 119.959 | 22/18/0 | no |
| `thinking-qwenvl-atdm` | 2401 | PASS | PASS | PASS | 65.171 | 0/0/45640 | no |
| `simplestream` | 2401 | PASS | PASS | PASS | 29.313 | 40/0/0 | no |
| `covstream` | 2401 | PASS | PASS | PASS | 35.074 | 40/0/0 | no |
| `B3-best-static` | 2401 | PASS | PASS | PASS | 119.967 | 12/28/0 | no |
| `B4-query-type-routing` | 2401 | PASS | PASS | PASS | 119.971 | 36/4/0 | no |
| `B6-latency-aware-routing` | 2401 | PASS | PASS | PASS | 119.957 | 6/34/0 | no |
| `B7-edf-feasibility` | 2401 | PASS | PASS | PASS | 119.967 | 12/28/0 | no |
| `B8-utility-per-gpu-second` | 2401 | PASS | PASS | PASS | 120.0 | 26/14/0 | no |
| `B9-best-of-breed` | 2401 | PASS | PASS | PASS | 35.074 | 40/0/0 | no |

**38 of 38 configurations ran, respected the interface and stayed inside the shared budget.** Two of them (`hindsight-oracle`, `rh8-demand-aware-ORACLE`) are upper bounds that read information the interface forbids, by construction and by declaration.

### 5.2 Case-B originals: what ran on CPU and what did not

| original | pinned commit | licence | smoke result |
|---|---|---|---|
| `frugalgpt` | `2b23e6acbd4b` | ? | **PASS** - loaded the repo's own committed cascade summary summary_HEADLINES_e8_full_2024.csv. 30 rows, columns ['Unnamed: 0', 'Test_acc', 'Test_cost', 'Test_size', 'Train_acc', 'Train_cost'] |
| `clockwork` | `6ce83e029051` | Apache-2.0 (MPI-SWS) | not run - cmake configure attempted. configure fails at find_package(Boost) - Boost is not installed on this host; the repo is ~26k lines of C++ and its docs require Boost, CUDA and TVM. The paper's emulated-worker mode would permit a GPU-free run, but building the toolchain is outside this task. |
| `ekya` | `2a6c8201db95` | NONE FOUND - all rights reserved by default | not run - NOT EXECUTED BY CHOICE. the repository has NO LICENSE file anywhere (searched LICENSE/COPYING and the README), so no use or modification right is granted. It was cloned for citation and commit pinning only; no file was opened, run or copied, and the adapted baseline was written from the PAPER. Its own CPU-runnable toy example (simulator/tiny_sim.ipynb, numpy + matplotlib only) was therefore left unrun. FLAGGED for the user. |
| `automix` | `531af3ee3c4e` | Apache-2.0 | not run - Scoring.ipynb inspected. its offline scorer needs only pandas, but reads data/automix_llama2_outputs_ver_n32.jsonl, and the repo ships no data/ directory, so its own example cannot run without downloading the generations. |
| `routellm` | `0b64fdafe049` | Apache-2.0 | not run - tests inspected. routellm/tests/{test_openai_client,test_openai_server}.py both require an OpenAI API key and network calls. The task forbids handling credentials, so they were not run; the mf router additionally downloads a checkpoint from HuggingFace. |
| `lmcache` | `6d8376b1248c` | Apache-2.0 | not run - tests inspected. the package targets CUDA (CMakeLists.txt + csrc/); its light tests import the lmcache package, which pulls torch. Not run on a CPU-only host. |
| `tmo` | `80830c6d863e` | MIT | not run - requirements inspected. requires torch 2.8.0, gymnasium and stable_baselines3; CPU-feasible in principle but a heavy install, and TMO is a BORDERLINE candidate, so it was not built (see the borderline decision in the report). |

Only FrugalGPT produced a positive CPU smoke (its own committed cascade summary parses). The rest are blocked by a GPU dependency, a build toolchain, missing data the repository does not ship, or credentials this task must not handle - each recorded with the exact blocker in `results/orchestration/study_b_baselines/b_originals_smoke.json`, and Ekya additionally by its missing licence.

## 6. Borderline candidates: decided, mostly not built

| candidate | id (verified) | case | decision and reason |
|---|---|---|---|
| `flashback` | Chen et al., FlashBack: Knowing When to Remember in Streaming Vision-Language Models, arXiv:2610.01192<br>*arXiv abstract page (1 Oct 2026)* | D (decided, NOT built) | BORDERLINE. Case D. Its decision - whether a query needs history BEFORE retrieving it - IS expressible as our representation + readiness choice, and it is close to R3-Streaming's Respond stage which is already built. Not built: the marginal value over r3-streaming is low. Half-day rule: under budget, but deliberately deferred. |
| `tmo` | Yuan, Han, Wang, Brinton, TMO / Three-M Offloading, MobiHoc 2025; journal version IEEE/ACM Trans. Networking<br>*OpenAlex: IEEE Transactions on Networking 2026; arXiv:2502.11007 v5* | B (decided, NOT built) | BORDERLINE. Author-linked code, MIT, cloned and pinned. Not built: its decision logic IS a trained constrained-RL policy, so an adapted version would have to RETRAIN (torch + stable_baselines3), and using it untrained would not be TMO. Deferred. |

**CoVStream is the one genuine interface conflict in this suite**, and it is reported rather than hybridised: its edge tier produces compact features *and captions* and its cloud tier maintains an *entity graph*. Our evidence inventory holds only representations we have measured ({RECENT, RICH, D2}); expressing CoVStream would mean inventing a caption/graph representation that no study of ours has built or costed. That changes what it fundamentally decides, so it is listed as related work.

## 7. Related work only: verified, with the one-line reason each is not a baseline

| work | venue / id | verification | why not a baseline |
|---|---|---|---|
| Chameleon | SIGCOMM 2018 | verified (OpenAlex) | picks video-analytics configurations by exploiting temporal correlation across cameras; it tunes a pipeline's knobs, not the device/cloud placement of a standing query. |
| Reducto | SIGCOMM 2020 | verified (OpenAlex) | on-camera frame filtering decides WHICH frames to send; our cadence and frame-count knobs already cover that axis and it makes no serving decision. |
| DDS (Server-Driven Video Streaming) | SIGCOMM 2020 | verified (OpenAlex) | a server-driven two-pass video codec loop for DNN inference; it optimises the encode, not scheduling or admission. |
| Nexus | SOSP 2019 | verified (OpenAlex) | GPU cluster scheduling for batched DNN video analysis; no stateful sessions and no device tier, so it cannot express our recall decisions. |
| Shepherd | NSDI 2023 | verified (USENIX page: Zhang, Tang, Khandelwal, Stoica) | serving-layer preemption and batching over request streams; its planning layer aggregates streams for predictability rather than choosing a tier. |
| VTC (Fairness in Serving LLMs) | OSDI 2024 (arXiv 2023 record verified) | partly verified - OpenAlex found the preprint, not the OSDI record | a fairness scheduler among tenants; our evaluation has one tenant, so its objective is undefined here. |
| Sarathi-Serve | OSDI 2024 (arXiv 2024 record verified) | partly verified - preprint only | chunked-prefill scheduling INSIDE one engine; it is an engine lever, already covered by the tuned-engine baseline's E2 configuration. |
| DistServe | OSDI 2024 (arXiv 2024 record verified) | partly verified - preprint only | prefill/decode disaggregation across GPUs; we have one replica and our costs are prefill-dominated, so there is nothing to disaggregate. |
| Splitwise | ISCA 2024 | verified (OpenAlex, DOI 10.1109/ISCA59077.2024.00019) | phase splitting across machine pools; a cluster-provisioning decision, not a per-request placement one. |
| EPD disaggregation | arXiv:2501.05460 (2024-12-25) | verified (arXiv API) | encode/prefill/decode disaggregation for multimodal serving; same reason as DistServe, and StudyE10d showed the LM prefill is the unsplittable unit on our hardware. |
| Llumnix | OSDI 2024 (arXiv 2024 record verified) | partly verified - preprint only | live migration of requests between instances for load balancing; one replica here. |
| Symphony | arXiv 2023 | verified (OpenAlex) | deferred batch scheduling for DNN serving; a batching policy, and our action space has no batch dimension. |
| CoSense-LLM | arXiv 2025 | verified (OpenAlex) | semantic edge-cloud compression for sensing; it decides what semantics to send, which our representation set already fixes to measured options. |
| EdgeCoInfer | arXiv 2026 | verified (OpenAlex) | hierarchical collaborative inference by model partitioning; FORMULATION scopes out splitting one model across tiers. |
| StreamScout | arXiv 2026 | verified (OpenAlex) | learns when to look deeper in a stream; closest to R3-Streaming's Reason stage, which is already a built baseline. |
| VLMCache | MobiSys 2026 | verified (OpenAlex) | on-device VLM caching; a device-side mechanism, not a placement or admission policy. |
| Pallas | arXiv:2608.16477 (2026-08-17) | verified (arXiv API) | proactive KV cache MIGRATION between serving nodes; one replica here, so migration has no destination. |
| ctHO | arXiv:2603.28018 (2026-03-30) | verified (arXiv API) | edge LLM handover with joint KV transfer; a mobility/handover mechanism, and StudyE6b already covers our mobility question. |
| llm-d / CacheRoute | NOT VERIFIED | **UNVERIFIED** - no index record found | a Kubernetes-native distributed inference stack / cache-aware router; infrastructure rather than a published policy we can reconstruct. |
| MSAO | NOT VERIFIED | **UNVERIFIED** - no index record found | multi-server adaptive offloading; could not confirm the paper exists under this name. |
| AceSpec | NOT VERIFIED | **UNVERIFIED** - no index record found | speculative decoding; a decode-time accelerator, orthogonal to placement. |
| Splitwise-DRL | NOT VERIFIED | **UNVERIFIED** - no index record found | a reinforcement-learning variant of Splitwise; same cluster-provisioning scope. |
| SpotVLM / edgeVLM | NOT VERIFIED | **UNVERIFIED** - no index record found | on-device VLM execution; a device-side runtime, not a scheduler. |
| SAIL | MobiSys 2026 (claimed) | **UNVERIFIED** - no index record found | could not confirm; if it exists it is an on-device VLM system rather than a scheduler. |
| HERMES | ACL 2026 (claimed) | **UNVERIFIED** - no index record found | could not confirm under this name. |

### Citations I could not verify (7)

Searched OpenAlex by title, the arXiv API by identifier where one was given, and the web; no index record was found for:

- **llm-d / CacheRoute**
- **MSAO**
- **AceSpec**
- **Splitwise-DRL**
- **SpotVLM / edgeVLM**
- **SAIL**
- **HERMES**

These are flagged rather than cited. Four of them (llm-d / CacheRoute, SAIL, VLMCache, HERMES) were given with a venue or product name but no identifier, and the remaining ones (MSAO, AceSpec, Splitwise-DRL, SpotVLM / edgeVLM) may be internal shorthands rather than paper titles. **If any of these is meant to be in the related-work section, it needs an identifier.** Note that VLMCache (MobiSys 2026) *did* verify and is listed above; SAIL, also given as MobiSys 2026, did not.

Two further partial verifications, stated plainly: OpenAlex returned the **preprint** record but not the proceedings record for VTC, Sarathi-Serve, DistServe and Llumnix. Their OSDI 2024 venues are from the publisher pages and my own reading, not from an index query in this session, so they are marked *partly verified*.

## 8. What a reviewer should check, and what is weakest

Per-baseline detail is in the cards; these are the five places where this suite is furthest from the originals, all of them consequences of our action space rather than of the papers:

1. **Sub-session KV granularity is not expressible.** AttentionStore manages KV *layer-wise* across three tiers and Pensieve at *token/chunk* granularity; our `session_action` is whole-session over two tiers. Both mechanisms are reconstructed and toy-tested, but the policies cannot use them. See `cards/attentionstore.md` A1 and `cards/pensieve.md` A1.
2. **Hybrid LLM's three routers collapse toward one on our data.** StudyD3 has one response per (clip, offset, arm), so Eq. (2)'s 10-sample expectation is unavailable and `r_prob` / `r_trans` receive single-sample labels. See `cards/hybrid_llm.md` A6.
3. **VideoStorm's profiler is not exercised.** Section 5's greedy configuration exploration needs inference; we substitute measured profiles, so only the scheduler is tested. See `cards/videostorm.md` A2.
4. **INAR-VL's image signals are substituted.** We do not re-read pixels, so blur / exposure / artifact / detail become device-trajectory statistics. This baseline is "INAR-VL's router structure on our signals", not INAR-VL. See `cards/inarvl.md` A1.
5. **Clockwork loses batching.** Our action space has no batch dimension, so §5.3's batch-size strategies and speculative growth are dropped. See `cards/clockwork.md` A4.

Two reconstruction gaps where a paper did not print something needed, each marked in its card and its module: Hybrid LLM's label-transformation closed form (§3.3 gives the objective and says `t` is grid-searched, not the function) and PerLLM's `P(t)` term (it appears in the CS-UCB figure undefined; set to zero).

## 9. Open questions for you

1. **The tuned engine (§0a).** Either StudyE10e is planned and this baseline should wait for it, or the intended baseline is "E10c's best measured configuration", which is the **default engine** - in which case `tuned-engine` and `naive.always-cloud-fcfs` differ only in name. Needs a decision; I will not guess a tuned combination.
2. **Ekya's licence (§0b).** Confirm that citation-only use is what you want, or ask the authors for a licence if the original needs to run.
3. **RH8 (§0c).** Confirm that the oracle arm is to be reported as an upper bound and the causal arm as a separate, clearly-labelled policy that StudyRH8 never measured.
4. **The 8 unverifiable citations (§7).** Identifiers needed, or drop them.
5. **FlashBack and TMO** are decided but not built (§6). Both are under the half-day bar; say the word and they go in.

## 10. Files

| path | what |
|---|---|
| `experiments/orchestration/baselines/interface.py` | the policy interface, enforced |
| `.../costs.py` | measured cost curves, one copy per constant |
| `.../profiles.py` | resource-quality profiles from StudyE9b / E9c |
| `.../devsplit.py` | StudyD3 development split - the only fitting set |
| `.../naive.py` | the seven naive baselines |
| `.../<name>_adapted.py` | one module per adapted baseline (14 modules) |
| `.../reconstructed/` | 7 faithful reconstructions + 7 toy tests |
| `.../cards/<name>.md` | 14 cards, one per case A / B / D baseline and per flagged own baseline |
| `.../registry.yaml` | 24 entries: name, paper, verification, code, pinned commit, licence, case, versions, files |
| `.../smoke/replay.py`, `run_all.py` | the 10-minute replay harness and its runner |
| `results/orchestration/study_b_baselines/b_smoke_results.json` | the adapted-baseline smoke results |
| `results/orchestration/study_b_baselines/b_originals_smoke.json` | what each cloned original could and could not do on CPU |
| `.../make_report.py` | this report |
| `~/baselines_src/<name>` | 7 third-party clones at pinned commits, OUTSIDE this repository |

---

# ADDENDUM (2026-11-12): new candidates, constructed baselines, fairness rules, experiment grouping

Everything above still holds. This part records what the addendum added.

## 11. Verification first: Route2Look, Fairway, QueryStream

The addendum requires Route2Look and Fairway to be **verified before anything is built**, and that if a paper cannot be found it is marked "unverified, not built" and nothing else is done. Applied, and extended to a third candidate that turned out the same way:

| candidate | requested as | verification attempted | outcome |
|---|---|---|---|
| `route2look` | - | **NOT FOUND**: OpenAlex title search returned no record | **UNVERIFIED - NOT BUILT** — Per the addendum: verified first, no paper found, so marked unverified and nothing else was done. |
| `fairway` | - | **NOT FOUND**: two OpenAlex title searches returned no record | **UNVERIFIED - NOT BUILT** — Per the addendum: verified first, no paper found, so marked unverified and nothing else was done. |
| `querystream` | P1 (requested) | **NOT FOUND**: OpenAlex title search returned no record | **UNVERIFIED - NOT BUILT** — Requested as a P1 component baseline, but no paper could be located, so building it would mean inventing its gating logic. Treated like Route2Look and Fairway: unverified, not built. NEEDS AN IDENTIFIER. |

**QueryStream was requested as a P1 component baseline**, but no index record exists for it under that name (the addendum gives no identifier, only "ICLR 2026"). Building it would mean inventing its gating and response logic, so it is treated exactly like Route2Look and Fairway. **All three need an identifier before they can enter the suite.**

## 12. The six fairness rules, enforced

The addendum's rules are enforced in `interface.py` and the harness, not merely documented, and every card restates them:

| rule | how it is enforced |
|---|---|
| **1** | Same models and evidence: the device tier is 4BI, the cloud tier is 32BI, every policy sees the same observation, and no externally trained VLM may be substituted. Enforced by `validate_action` (no model field exists in the action space) and by `check_fairness`, which rejects a policy declaring a model outside MODELS. |
| **2** | Same resources: ONE H100 replica. A multi-instance algorithm must be adapted and LABELLED as such via `Policy.multi_instance_adapted = True`; the action space has no instance dimension, so a policy cannot route across replicas. |
| **3** | Same state accounting: every policy pays synchronisation, upload, cache construction, GPU/host occupancy, recomputation and INITIAL WARMING. Cloud-only gets no free history. Enforced by the harness, which charges a session's first promotion to GPU-warm at the measured cold-prefill cost and charges uplink bytes per episodic cloud call. |
| **4** | Same feasible actions and deadlines, unless restricting the action space IS the property being tested - in which case the policy must declare `restricts_action_space` with a reason, which the harness records. |
| **5** | No future knowledge except the oracle: `scrub()` on every epoch, and any policy that reads the future must declare `reads_future = True` and is excluded from the causality check and from every deployable comparison. |
| **6** | Identical demand traces, seeds, deadlines and bootstrap units across policies: the harness builds the trace once from a fixed seed and asserts the digest is identical for every policy it runs. |

`interface.check_fairness(policy)` runs before every smoke replay and raises on a policy that names a model outside {4BI, 32BI}, restricts the action space without a stated reason, or claims an unknown experiment. The harness additionally charges a session's **first** promotion to GPU-warm at the measured cold-prefill cost (rule 3: no policy gets free history), charges uplink bytes on every episodic cloud call, and asserts the demand trace's SHA-256 digest is identical for every policy (rule 6).

Two policies declare `reads_future = True` and are excluded from every deployable comparison: `hindsight-oracle` and `rh8-demand-aware-ORACLE`. One declares `restricts_action_space`: `thinking-qwenvl-atdm`, because being a readiness-only component IS the property under test (rule 4). Two declare `multi_instance_adapted`: `preble` and `mooncake`, because both are multi-replica systems adapted to our single replica (rule 2).

## 13. New candidates

| baseline | priority | paper (verification) | code | case | versions | card |
|---|---|---|---|---|---|---|
| `eco-llm` | P0 | Patidar, Crown, Hsieh, Xu, ECO-LLM: Orchestration for Domain-specific Edge-Cloud Language Models, arXiv:2507.09003 (11 Jul 2025, Microsoft Research)<br>*arXiv API: id, title, authors, date. NAME NOTE: a DIFFERENT 2024 paper also uses the ECO-LLM name; the id resolves to the MSR one* | none found | **D** | reconstruction, adapted | `cards/ecollm.md` |
| `streamscout` | P0 | StreamScout: Learning When to Look Deeper for Streaming Video Understanding, arXiv:2609.00291<br>*arXiv API (id found by title search; the addendum gave none)* | none found | **D** | reconstruction, adapted | `cards/streamscout.md` |
| `preble` | P0 | Srivatsa, He, Abhyankar, Li et al., Preble: Efficient Distributed Prompt Scheduling for LLM Serving, arXiv:2407.00023<br>*OpenAlex + arXiv API* | `https://github.com/WukLab/preble`<br>@`1a35eae20c41`<br>Apache-2.0 | **B** | original (cloned), adapted | `cards/preble.md` |
| `mooncake` | P0/P1 | Qin et al., Mooncake: A KVCache-centric Disaggregated Architecture for LLM Serving, ACM Transactions on Storage 2025 / FAST 25 (arXiv:2407.00079)<br>*OpenAlex: ACM Transactions on Storage 2025* | `https://github.com/kvcache-ai/Mooncake`<br>@`5ffbf763368d`<br>Apache-2.0 | **B** | original (cloned), adapted | `cards/mooncake.md` |
| `kvflow` | P1 | Pan et al., KVFlow: Efficient Prefix Caching for Accelerating LLM-Based Multi-Agent Workflows, arXiv:2507.07400<br>*arXiv API verifies the id; the NeurIPS 2025 venue the addendum gives is **UNVERIFIED*** | none found | **D** | reconstruction, adapted | `cards/kvflow.md` |
| `uniscale` | P1 | Huang et al., UniScale: Adaptive Unified Inference Scaling via Online Joint Optimization of Model Routing and Test-Time Scaling, arXiv:2605.30898<br>*arXiv API verifies the id; the ICML 2026 venue the addendum gives is **UNVERIFIED*** | none found | **D** | reconstruction, adapted | `cards/uniscale.md` |
| `thinking-qwenvl-atdm` | P1 | Zhang et al., Progressive Online Video Understanding with Evidence-Aligned Timing and Transparent Decisions, arXiv:2604.18459<br>*arXiv API verifies the id; the ICLR 2026 venue the addendum gives is **UNVERIFIED*** | none found | **D** | reconstruction, adapted | `cards/thinking_qwenvl.md` |
| `simplestream` | required | Shen, Tian, Yang, Liu, A Simple Baseline for Streaming Video Understanding, arXiv:2604.02317<br>*arXiv API* | `https://github.com/EvolvingLMMs-Lab/SimpleStream`<br>@`be227ee8ce90`<br>NONE FOUND - all rights reserved | **B** | original (cloned, NOT executed), adapted | `cards/simplestream.md` |
| `covstream` | conditional P1 | Liu, Chen, Yan, Wu, Wang, CoVStream: Edge-Cloud Collaboration for Understanding of Long Video Streams, arXiv:2606.22804<br>*arXiv abstract page* | none found | **D** | reconstruction, adapted | `cards/covstream.md` |

### Reconstruction toy tests (addendum)

| reconstruction | behaviours | named from the paper |
|---|---|---|
| `reconstructed/ecollm.py` | **-** | joint exploration over model AND pipeline knobs; **joint selection beats model selection alone under a cost SLO** (the paper's central claim); highest quality among feasible; least-violating when nothing is feasible; ties break to lower cost |
| `reconstructed/streamscout.py` | **7/7 behaviours** | three views recent -> uniform -> query-relevant; answers at the first sufficient stage; the deepest view always answers; **thresholds distilled on a TRAINING set reproduce the earliest adequate stage**; harder examples escalate further |
| `reconstructed/kvflow.py` | **6/6 behaviours** | steps-to-execution read off the workflow order; **eviction keeps the node about to run and drops the far one, where LRU would do the opposite**; evicts until the tier fits; prefetch nearest-first; fully overlapped prefetch |
| `reconstructed/uniscale.py` | **7/7 behaviours** | arms are (model, compute) PAIRS so the optimisation is joint; LinUCB optimism and shrinking confidence width; concentration on the rewarding arm; **the efficiency reward makes the strongest arm lose when compute is priced**; played-arm-only update |
| `reconstructed/thinking_qwenvl.py` | **7/7 behaviours** | waits on low progress; waits on low confidence; answers when both clear; **t\* is the first sufficient-evidence timestamp**; every decision carries a reason (the transparency claim); raising thresholds delays t\* |
| `reconstructed/covstream.py` | **-** | bandwidth far below raw upload; the edge encodes every frame regardless of queries; **the construction compute is CHARGED and non-zero with no query**; answering uploads nothing; richer features cost more bandwidth |

## 14. Constructed baselines, and B9's component choices

| id | what it is | experiments |
|---|---|---|
| `B3-best-static` | see `cards/constructed.md` | A-episodic, B-recall, C-mixed |
| `B4-query-type-routing` | see `cards/constructed.md` | C-mixed |
| `B6-latency-aware-routing` | see `cards/constructed.md` | C-mixed |
| `B7-edf-feasibility` | see `cards/constructed.md` | C-mixed |
| `B8-utility-per-gpu-second` | see `cards/constructed.md` | A-episodic, C-mixed |
| `B9-best-of-breed` | see `cards/constructed.md` | C-mixed |

**B9 is the primary competitor and is built to be as strong as this suite allows.** Its four mechanisms, and why each choice was made over the alternative the addendum offered:

| component | choice | why over the alternative |
|---|---|---|
| (i) model / evidence routing | **ECO-LLM-style** joint (tier, representation, cadence, N) selection under SLOs | the addendum offered ECO-LLM-style *or* the calibrated query-type router; the former optimises over the joint space rather than a per-type rule, so it is strictly more informed |
| (ii) streaming readiness + rate | **VideoStorm MaxMin** (Eq. 4) rate allocation, gated by an **R3-Streaming-style readiness** test | both were asked for; MaxMin over MaxSum because it protects the worst stream, and StudyE9b / E9c show rate allocation — not escalation — is the episodic lever |
| (iii) SLO-aware cloud scheduling | **utility-per-GPU-second** admission with **EDF** order among the admitted | the addendum offered EDF *or* utility-per-cost; using the ratio for admission and EDF for ordering is stronger than either alone |
| (iv) KV management | **host offload** + **Preble-style cache affinity** under load + **KVFlow-style reuse-aware eviction** on the causal inter-arrival estimate | the three modern mechanisms this suite holds, composed; the reuse signal is causal because rule 5 forbids KVFlow's workflow lookahead |

The four run **independently**: each optimises its own objective from the shared observation and none sees another's choice. Where two would touch the same field, a fixed precedence resolves it — (ii) sets the episodic rate and (i) may only *downgrade* it; (i) chooses the recall representation, (iii) may refuse on budget and (iv) on cache affinity; (iv) alone places sessions; (iii) alone orders. **That precedence is exactly what a jointly-optimising scheduler is meant to beat**, so it is stated rather than tuned away: any advantage our scheduler shows over B9 must come from coordinating the four decisions, not from better components.

## 15. The suite grouped by experiment

Metrics are the addendum's: **A** uses challenge mAP (StudyE9c's definition) as the headline with streaming AP (StudyE9b) beside it, on StudyD14b under the StudyE9b delivery model, plus false alarms and GPU-seconds; **B** uses S-EMBER accuracy on **PNG** inputs (StudyE10a-full did not validate JPEG), deadline success, memory, communication and maintenance compute; **C** reports per-class outcomes and flags any policy that starves a class.

### Experiment A — episodic — 18 baselines

| baseline | case | priority |
|---|---|---|
| `confidence-cascade` | B | - |
| `ekya` | B | - |
| `routellm` | B | - |
| `eco-llm` | D | P0 |
| `hybrid-llm` | D | - |
| `inar-vl` | D | - |
| `r3-streaming` | D | - |
| `thinking-qwenvl-atdm` | D | P1 |
| `uniscale` | D | P1 |
| `videostorm` | D | - |
| `B3-best-static` | constructed | - |
| `B8-utility-per-gpu-second` | constructed | - |
| `always-cloud-fcfs` | naive | - |
| `device-only` | naive | - |
| `hindsight-oracle` | naive | - |
| `random-admission` | naive | - |
| `round-robin` | naive | - |
| `static-partition` | naive | - |

### Experiment B — recall — 13 baselines

| baseline | case | priority |
|---|---|---|
| `rh8-demand-aware` | A | - |
| `lmcache` | B | - |
| `simplestream` | B | required |
| `attentionstore` | D | - |
| `covstream` | D | conditional P1 |
| `eco-llm` | D | P0 |
| `kvflow` | D | P1 |
| `pensieve` | D | - |
| `r3-streaming` | D | - |
| `streamscout` | D | P0 |
| `B3-best-static` | constructed | - |
| `always-cloud-fcfs` | naive | - |
| `hindsight-oracle` | naive | - |

### Experiment C — mixed — 23 baselines

| baseline | case | priority |
|---|---|---|
| `clockwork` | B | - |
| `ekya` | B | - |
| `mooncake` | B | P0/P1 |
| `preble` | B | P0 |
| `routellm` | B | - |
| `eco-llm` | D | P0 |
| `hybrid-llm` | D | - |
| `inar-vl` | D | - |
| `perllm` | D | - |
| `uniscale` | D | P1 |
| `B3-best-static` | constructed | - |
| `B4-query-type-routing` | constructed | - |
| `B6-latency-aware-routing` | constructed | - |
| `B7-edf-feasibility` | constructed | - |
| `B8-utility-per-gpu-second` | constructed | - |
| `B9-best-of-breed` | constructed | - |
| `always-cloud-fcfs` | naive | - |
| `device-only` | naive | - |
| `edf-service-time` | naive | - |
| `hindsight-oracle` | naive | - |
| `random-admission` | naive | - |
| `static-partition` | naive | - |
| `tuned-engine` | own | - |

**Our scheduler is not in these lists**; it is added later and compared against them.

