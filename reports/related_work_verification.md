# Related Work Verification
<!-- generated 2026-08-19 -->

This report verifies each paper cited in an external review against primary sources (arXiv, conference pages, IEEE Xplore). The review's characterization is not inherited; summaries are drawn from abstracts and paper content. Confidence flags appear only where a paper could not be located or the review's description materially mismatches the source.

---

## 1. CachedAttention

**(a)** Bin Gao, Zhuomin He, Puru Sharma, Qingxuan Kang, Djordje Jevdjic, Junbo Deng, Xingkun Yang, Zhou Yu, Pengfei Zuo. "Cost-Efficient Large Language Model Serving for Multi-turn Conversations with CachedAttention." USENIX Annual Technical Conference (ATC), 2024, pp. (conference proceedings).

**(b)** CachedAttention saves the KV cache generated at each conversation turn into a hierarchical storage system (GPU VRAM → CPU DRAM → SSD), reusing it on subsequent turns rather than recomputing from tokens. It uses scheduler-aware fetching and eviction—the inference scheduler hints which sessions are active so KV can be pre-loaded into faster tiers and evicted when idle—and employs layer-wise asynchronous pre-loading to overlap cache access with GPU computation.

**(c)** Both systems treat multi-turn session KV state as an object worth persisting across turns rather than recomputing, and both use a tiered storage hierarchy with explicit placement decisions.

**(d)** CachedAttention operates within a single serving node's storage hierarchy and makes no distinction in semantic fidelity across representations—it stores exactly the full-context KV and optimizes its byte movement; our work operates across mobile candidate nodes and treats fidelity (what a state object can answer) as the primary resource dimension alongside bytes.

---

## 2. Mooncake

**(a)** Ruoyu Qin, Zheming Li, Weiran He, Mingxing Zhang, Yongwei Wu, Weimin Zheng, Xinran Xu. "Mooncake: A KVCache-centric Disaggregated Architecture for LLM Serving." USENIX FAST 2025 (also published in ACM Transactions on Storage; arXiv:2407.00079, 2024).

**(b)** Mooncake is the production serving platform for Kimi (Moonshot AI) that disaggregates prefill and decoding clusters and builds a global KV cache pool across GPU, CPU DRAM, SSD, and NIC resources, so that reusable prefix KV computed during prefill need not be recomputed on a subsequent matching request. The scheduler trades storage cost against recomputation cost: it predicts whether fetching cached KV from a slower tier will be faster than re-prefilling, and rejects requests early when overload makes SLO violation inevitable.

**(c)** Both systems explicitly reason about the trade between storing KV state (at different cost tiers) and recomputing it, and both build policies to maximize SLO satisfaction under capacity constraints.

**(d)** Mooncake operates entirely within a fixed datacenter serving cluster optimizing throughput; it does not model mobile candidate-node sets that change with user movement, does not represent multiple semantic fidelities of the same session, and does not anticipate provisioning needs at nodes the user has not yet reached.

---

## 3. IMPRESS

**(a)** Weijian Chen, Shuibing He, Haoyang Qu, Ruidong Zhang, Siling Yang, Ping Chen, Yi Zheng, Baoxing Huai, Gang Chen. "IMPRESS: An Importance-Informed Multi-Tier Prefix KV Storage System for Large Language Model Inference." USENIX FAST 2025 (23rd USENIX Conference on File and Storage Technologies), Feb 2025, Santa Clara, CA, pp. 187–201.

**(b)** IMPRESS addresses the case where prefix KV caches must be stored on disk due to insufficient CPU DRAM: naively loading the full prefix back from SSD can cost more in I/O latency than the prefill saving is worth. It computes an importance score per KV entry (exploiting similarity across attention heads) and loads only the high-importance subset from disk, achieving up to 2.8× TTFT reduction while "maintaining comparable inference accuracy."

**(c)** IMPRESS introduces a quality-aware selection of which KV entries to load versus skip, which is structurally similar to our observation that not all context tokens are equally necessary for task quality; both systems make a cost-vs-retained-information tradeoff.

**(d)** IMPRESS operates within a single inference node's storage tiers and its granularity is token-level KV importance within a fixed prefix; it does not assign different semantic fidelity representations to the same session, does not reason about mobile placement across candidate nodes, and the "quality" it maintains is token-level approximation accuracy rather than task-level question-answering capability under different workload regimes.

**Note on review characterization:** The review said IMPRESS "trades retained KV information against quality and I/O." This is approximately correct—it does drop some KV entries to reduce I/O—but the framing inverts the intent: IMPRESS aims to maximize quality retention subject to I/O cost, selecting the subset of KV most likely to preserve output quality, not explicitly trading quality as a knob.

---

## 4. AdaptCache

**(a)** Shaoting Feng, Hanchen Li, Kuntai Du, Zhuohan Gu, Yuhan Liu, Jiayi Yao, Siddhant Ray, Samuel Shen, Yihua Cheng, Ganesh Ananthanarayanan, Junchen Jiang. "AdaptCache: KV Cache Native Storage Hierarchy for Low-Delay and High-Quality Language Model Serving." BigMem Workshop at SOSP 2025; arXiv:2509.00105, 2025.

**(b)** AdaptCache jointly decides, per KV cache entry: (1) which lossy compression algorithm to apply, (2) the compression rate, and (3) whether to place the compressed entry in DRAM or SSD. The objective is to maximize DRAM hit rate—minimizing loading delay—without significantly degrading generation quality. Compared to static compression baselines, it reports 1.43–2.4× delay reduction at equivalent quality.

**(c)** AdaptCache makes a joint optimization over compression level and placement location to balance delay against quality, which is the same tradeoff structure our work addresses; both treat quality as a constraint rather than folding it into a scalar objective.

**(d)** AdaptCache's "joint" optimization is over KV byte-level compression decisions within a single server's DRAM/SSD hierarchy—all decisions preserve the same session's semantic content, differing only in quantization fidelity and storage tier. Our joint optimization is over the semantic fidelity of the state object (which determines what future questions can be answered at quality) and the identity of the mobile candidate node where it is provisioned; these are orthogonal dimensions. AdaptCache has no mobility model, no model of how fidelity choice changes task-level accuracy across workload regimes, and no anticipatory provisioning across future candidate nodes.

**This is the highest-collision citation.** The word "jointly" in our work must be scoped carefully: "jointly chooses fidelity representation and provisioning location across candidate mobile nodes" is distinct from AdaptCache's "jointly chooses compression algorithm, rate, and placement within a server's storage hierarchy."

---

## 5. FlowKV, SmartGen, BanaServe

### FlowKV

**(a)** Weiqing Li, Guochao Jiang, Xiangyong Ding, Zhangcheng Tao, Chuzhan Hao, Chenfeng Xu, Yuewei Zhang, Hao Wang (Alibaba Cloud). "FlowKV: A Disaggregated Inference Framework with Low-Latency KV Cache Transfer and Load-Aware Scheduling." arXiv:2504.03775, April 2025.

**(b)** FlowKV targets the prefill–decode disaggregation setting where the KV cache produced during prefill on one set of GPUs must be transferred to decode GPUs; it introduces a pull-based transfer protocol and a load-aware scheduler that allocates requests to P/D node pairs based on current load. It reduces average KV transfer latency by 96% (0.944 s → 0.053 s) and improves throughput by 15.2–48.9% on LongBench.

**(c)** Both systems must move KV state across network boundaries between compute nodes.

**(d)** FlowKV operates within a fixed datacenter disaggregated cluster, transfers full KV in bulk, and makes no quality or semantic-fidelity decisions; the network is fast and stable, not a mobile backhaul with variable bandwidth and changing reachability.

### SmartGen

**(e) CONFIDENCE: UNVERIFIED.** No paper titled "SmartGen" with the claimed behavior (selective KV entry transfer) could be located on arXiv, ACM DL, IEEE Xplore, or USENIX proceedings as of the verification date. The name does not appear in KV-cache survey repositories or search results. The review's citation of "SmartGen" alongside FlowKV and BanaServe cannot be confirmed. This citation should be treated as unverified until the reviewer supplies a direct link or DOI.

### BanaServe

**(a)** Yiyuan He et al. "BanaServe: Unified KV Cache and Dynamic Module Migration for Balancing Disaggregated LLM Serving in AI Infrastructure." Software: Practice and Experience, 2026 (Wiley); arXiv:2510.13223, 2025.

**(b)** BanaServe addresses dynamic load imbalance between prefill and decode stages in disaggregated LLM serving by introducing three mechanisms: layer-level weight migration (coarse-grained compute redistribution), attention-level KV cache migration (fine-grained memory load balancing), and a Global KV Cache Store with layer-wise overlapped transmission. It rebalances both compute and memory resources reactively as workloads shift.

**(c)** BanaServe migrates KV state across nodes when load imbalance is detected, which is structurally similar to our provisioning decisions that move session state between candidate nodes.

**(d)** BanaServe is reactive to observed load imbalance within a datacenter P/D cluster and makes no decisions about semantic fidelity; it migrates the full KV cache (or module weights) and has no mobile endpoint, no mobility trace, and no model of which future fidelity level a session will need.

---

## 6. "Serving Long-Context LLMs at the Mobile Edge"

**(a)** Minrui Xu, Dusit Niyato, Christopher G. Brinton. "Serving Long-Context LLMs at the Mobile Edge: Test-Time Reinforcement Learning-based Model Caching and Inference Offloading." IEEE/ACM Transactions on Networking, Vol. 34, 2026, pp. 3808–3823. (arXiv:2501.14205, submitted January 2025.)

**(b)** This paper optimizes the deployment of long-context LLMs at mobile edge networks by jointly deciding which model weights to cache on which edge servers and where to offload inference requests (device, edge, or cloud), using test-time deep RL (T2DRL) that adapts during deployment as context accumulates and usage patterns shift. The mobile scenario is a resource-limited edge network where multi-round LLM agent interactions create growing context windows that affect latency, accuracy, and resource consumption.

**(c)** Both papers address LLM serving under mobile constraints where multi-round session history creates a growing state management challenge, and both frame the decision as a joint optimization (model caching + offloading in their case; fidelity + placement in ours).

**(d)** This paper's "state" is the model weights cached on edge servers—it decides which LLM to host at which edge node; it does not manage session KV state or conversation history, does not represent multiple semantic fidelities of the same session history, and its quality dimension is which model version is locally available (not which subset of session history can be answered at SLO). The session history motivates the problem but is not the managed resource.

**Venue note:** The review's claim of "IEEE/ACM Transactions on Networking" is correct—this is the co-sponsored IEEE/ACM journal. The claim of "2026" is correct for the journal publication date (arXiv preprint is January 2025).

---

## 7. ATC 2025 Real-World KV-Cache Characterization

**(a)** Jiahao Wang, Jinbo Han, Xingda Wei, Sijie Shen, Dingyan Zhang, Chenguang Fang, Rong Chen, Wenyuan Yu, Haibo Chen. "KVCache Cache in the Wild: Characterizing and Optimizing KVCache Cache at a Large Cloud Provider." USENIX Annual Technical Conference (ATC), 2025. (arXiv:2506.02634.)

**(b)** This paper presents the first systematic characterization of production KV cache workload patterns from a major cloud LLM provider, finding that cache reuse is skewed across request types (single-turn prefix reuse is comparably important to multi-turn reuse), that reuse time and probability are diverse overall but predictable within request categories, and that the cache size needed for a good hit ratio is moderate. Based on this characterization, it proposes a workload-aware eviction policy tuned to real-world access patterns.

**(c)** Both papers establish empirical baselines for how real session state is accessed and reused, which motivates the need for intelligent state management policies.

**(d)** This work characterizes a single datacenter cache tier under a fixed eviction budget; it does not address mobile edge scenarios, does not represent multiple semantic fidelities of session state, and its optimization target is byte-level cache hit rate rather than task-level quality SLO satisfaction across mobile candidate nodes.

---

## 8. Geo-Distributed KV Transfer Measurement

**(a)** Shengnan Yue, Mowei Wang, Yu Yan, Weiqiang Cheng, Zihan Jiang, Zhenhui Zhang. "RTT- or Bandwidth-Bound? Demystifying the KV Cache Transfer in Large Language Model Serving." NAIC '25: Proceedings of the 2nd Workshop on Networks for AI Computing (co-located with SIGCOMM 2025), 2025.

**(b)** This paper empirically characterizes why KV cache transfer in geo-distributed prefill–decode disaggregation is RTT-bound rather than bandwidth-bound despite abundant physical bandwidth: the root cause is that PagedAttention allocates non-contiguous memory blocks, so KV transfer degenerates to many small sends that collapse under high RTT, mirroring the TCP small-window problem. The result explains why effective KV transfer throughput is far below theoretical network capacity in geo-distributed settings.

**(c)** The RTT-bound finding directly supports our cost model for mobile edge scenarios where RTT from device to edge may be 10–100 ms—it explains why KV transfer costs in our inertia model are not purely bandwidth-determined.

**(d)** This paper is a measurement study, not an optimization system; it characterizes datacenter P/D disaggregation transfer, does not address mobile edge handover or session fidelity, and does not propose a policy for what to transfer or at what fidelity.

---

## 9. Agent Memory (arXiv 2606.06448)

**(a)** Yasmine Omri, Ziyu Gan, Zachary Broveak, Robin Geens, Zexue He, Alex Pentland, Marian Verhelst, Tsachy Weissman, Thierry Tambe. "Agent Memory: Characterization and System Implications of Stateful Long-Horizon Workloads." arXiv:2606.06448, June 2026.

**(b)** This paper provides the first comprehensive systems-level characterization of agent memory infrastructure, profiling ten representative memory systems across construction, retrieval, and generation phases to measure cost allocation. It identifies freshness–latency tradeoffs in memory operations and derives operational recommendations covering scheduling, capability requirements, query-volume amortization, and large-scale fleet deployment strategies.

**(c)** This paper characterizes the construction/retrieval/generation cost structure of agent memory systems—directly informing how expensive different memory representations are to maintain, which motivates the cost side of our fidelity–cost tradeoff.

**(d)** This work characterizes memory system performance on a single node (or single-session basis) and makes no provisioning decisions; it does not address mobile placement, multi-candidate-node readiness, or the interaction between memory fidelity and task-level quality under workload uncertainty.

**Review characterization match:** The review's description (construction/retrieval/generation profiling, freshness/latency, fleet-scale implications) matches the paper's content accurately.

---

## 10. Agentic Memory

**(a)** Yi Yu, Liuyi Yao, Yuexiang Xie, Qingquan Tan, Jiaqi Feng, Yaliang Li, Libing Wu. "Agentic Memory: Learning Unified Long-Term and Short-Term Memory Management for Large Language Model Agents." ACL 2026 (SAC Highlight); arXiv:2601.01885, January 2026.

**(b)** AgeMem (Agentic Memory) treats memory operations—store, retrieve, update, summarize, discard—as tool-callable actions within the agent's policy, using a three-stage progressive RL algorithm (step-wise GRPO) to train the agent to manage both long-term and short-term memory end-to-end, rather than relying on hand-coded heuristics or separate retrieval modules. Experiments show improved task performance, memory quality, and context efficiency.

**(c)** AgeMem determines what content to retain in summarized or full form versus discard, which bears on the same semantic compression question our fidelity taxonomy addresses (sum80/sum200/full/window); both systems grapple with the lossy compression of session history.

**(d)** AgeMem is an agent-level policy that optimizes what a single agent remembers during a task; it does not address where in a mobile topology those memories are provisioned, does not manage KV materialization or prefill costs, and does not reason about capacity-constrained edge nodes or handover timing.

**Distinction from item 9:** arXiv 2606.06448 (item 9) is a systems characterization paper profiling the cost structure of memory operations across ten existing systems; AgeMem (item 10) is a new memory management framework that learns memory operations via RL. They are complementary but distinct works.

---

## 11a. March 2026: KV Transfer vs Token-Prefill Recovery During Mobile Edge Handover

**(a)** Seunghun Lee, Jihong Park, Ce Zheng, Hyuncheol Park. "Low-Latency Edge LLM Handover via Joint KV Cache Transfer and Token Prefill." arXiv:2603.28018, March 2026. (Signal processing / networking.)

**(b)** This paper addresses what happens when a mobile device hands over between edge base stations during an LLM session: the new (target) edge server must reconstruct the session context, which can be done either by receiving the token stream and re-running prefill, or by receiving the KV cache directly over the backhaul. It proposes a joint optimization (ctHO) that simultaneously selects how many tokens to re-prefill at the target and how to schedule KV cache delivery over the available backhaul to minimize worst-user handover delay across multiple UEs.

**(c)** This paper is the closest mechanical antecedent to our physical-inertia cost model: it models handover delay as a function of prefill length and backhaul KV transfer, identifies exactly the tradeoff between "send tokens and recompute" versus "send KV cache directly" that appears in our materialization cost formulation.

**(d)** This paper treats the context state as a single binary choice—transfer-as-KV or recompute-from-tokens—and optimizes the split purely for latency; it does not model multiple semantic fidelities of the same session (the alternative is not a cheaper/lossier representation but just a slower/faster recovery of the same full state), and it does not anticipate provisioning at candidate nodes before handover occurs.

---

## 11b. August 2026: Accuracy-Aware Partial KV Transfer Under Limited Backhaul

**(e) CONFIDENCE: UNVERIFIED.** No paper matching this description—submitted around August 11, 2026, addressing accuracy-aware partial KV cache transfer under limited backhaul for mobile edge handover—could be located. The closest 2026 candidates found are:

- arXiv:2608.01126 (Le Yang, Zhouyong Liu, "Spatial Prefix Caching for Wireless Edge LLM Inference," submitted August 2, 2026): addresses which wireless edge nodes should cache which prefix KV to minimize TTFT using stochastic geometry; it does not perform accuracy-aware partial KV transfer.
- arXiv:2608.03893 (Taekyung Heo et al., "Cross-Model KV Cache Transfer," submitted August 4, 2026): addresses KV reuse when switching between LLM model families in a datacenter; not mobile, not accuracy-aware partial transfer.
- arXiv:2603.28018 (item 11a, submitted March 2026): the handover paper, but submitted in March not August, and does not address accuracy-aware partial transfer.

The review's claimed citation should be treated as unverified until a direct arXiv ID, DOI, or author list is supplied.

---

## Synthesis

### i. Positioning Table

| Work | Manages KV bytes or semantic fidelity | Single node / Distributed-DC / Mobile | Reactive / Anticipatory |
|---|---|---|---|
| CachedAttention (ATC'24) | KV bytes (full-context KV, tiered storage) | Single node (hierarchical storage) | Reactive (scheduler-aware eviction) |
| Mooncake (FAST'25) | KV bytes (full-context KV, disaggregated pool) | Distributed-DC | Reactive (prediction-based rejection) |
| IMPRESS (FAST'25) | KV bytes (importance-selected subset, single fidelity) | Single node (multi-tier storage) | Reactive (per-inference load decision) |
| AdaptCache (BigMem@SOSP'25) | KV bytes (lossy-compressed, DRAM/SSD placement) | Single node (DRAM+SSD hierarchy) | Reactive (per-entry compression decision) |
| FlowKV (arXiv 2504.03775) | KV bytes (full transfer, disaggregated P/D) | Distributed-DC | Reactive (pull-based, load-aware) |
| BanaServe (SPE'26) | KV bytes (attention-level migration) | Distributed-DC | Reactive (load-rebalancing trigger) |
| SmartGen | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| Xu et al. (ToN'26) | Model weights (caching) + inference placement | Mobile edge | Anticipatory (RL-based model caching) |
| Wang et al. (ATC'25) | KV bytes (eviction characterization) | Distributed-DC | Reactive (eviction policy) |
| Yue et al. (NAIC'25) | KV bytes (transfer measurement) | Geo-distributed DC | Measurement only |
| Omri et al. 2606.06448 | Semantic memory content (construction/retrieval) | Single agent | Characterization only |
| AgeMem / Agentic Memory (ACL'26) | Semantic fidelity (what to store/summarize/discard) | Single agent | Anticipatory (RL-learned policy) |
| Lee et al. 2603.28018 | KV bytes (transfer-vs-prefill split) | Mobile edge (handover) | Reactive (post-trigger optimization) |
| 11b (unverified) | Unknown | Unknown | Unknown |

### ii. Gap

Existing KV-management systems (CachedAttention, Mooncake, IMPRESS, AdaptCache, FlowKV, BanaServe) treat session state as a single semantic object whose capability is fixed—they optimize the byte cost, compression, tier placement, and transfer latency of that one object but do not represent the fact that cheaper representations of the same history answer different sets of future questions. Agent-memory work (AgeMem, Omri et al.) optimizes what an agent remembers and at what semantic granularity, but these systems operate at the single-agent level and do not address where in a mobile compute topology those memories should be provisioned or materialized, nor the interaction between memory fidelity and readiness cost at candidate edge nodes. The mobile LLM edge paper (Xu et al. ToN'26) is anticipatory and mobile but manages model-weight caching, not session-state fidelity. The handover papers (Lee et al. 2603.28018) model the transfer-vs-recompute choice for a single full-context state during a triggered handover event, without anticipatory pre-provisioning or multi-fidelity representation. No verified work combines anticipatory provisioning of multiple semantic fidelities of the same session state across a set of mobile candidate nodes under ready-capacity constraints that change with user movement.

### iii. Claims We Must Not Make

- **"No prior work stores KV across storage tiers"**: CachedAttention (ATC'24) and Mooncake (FAST'25) do exactly this; the differentiator is fidelity and mobility, not tiering.
- **"No prior work jointly optimizes compression and placement"**: AdaptCache (BigMem@SOSP'25) does this jointly within a single server's DRAM/SSD hierarchy; our claim must be scoped to "semantic fidelity choice and mobile candidate-node provisioning."
- **"First system to address mobile edge LLM serving"**: Xu et al. (ToN'26) and Lee et al. (arXiv:2603.28018) both address mobile edge; the differentiator is session-state fidelity management versus model-weight or latency-minimization focus.
- **"No prior work trades quality against KV retention"**: IMPRESS and AdaptCache both make quality-aware KV decisions; the differentiator is task-level semantic fidelity (which questions can be answered) versus token-level approximation accuracy.
- **"SmartGen selectively transfers KV entries"**: This citation is unverified; do not cite it.
- **"The August 2026 accuracy-aware partial KV transfer paper..."**: This citation is unverified; do not cite it until confirmed.

### iv. Additional Papers Encountered During Verification

The following papers were found during verification and appear directly relevant but were not in the review.

---

#### iv-A. Spatial Prefix Caching for Wireless Edge LLM Inference

**(a)** Le Yang, Zhouyong Liu. "Spatial Prefix Caching for Wireless Edge LLM Inference: A Stochastic-Geometry and Queueing Framework." arXiv:2608.01126, August 2, 2026.

**(b)** This paper asks which wireless edge GPU nodes should cache which prompt prefixes to minimize TTFT across spatially distributed users. It models edge nodes as a Poisson point process and derives a fixed-point formulation capturing the interaction between spatial node association and GPU memory contention between persistent prefix caches and active request queues, finding that the latency-optimal node is not necessarily the geographically nearest due to cache-depth vs. proximity tradeoffs.

**(c)** This paper directly addresses placement of KV state (prefix caches) across distributed wireless edge nodes under capacity constraints, with the tradeoff between communication cost and cache reuse—structurally analogous to our provisioning of session state across mobile candidate nodes.

**(d)** Spatial Prefix Caching manages prefix KV for shared-prefix prompt reuse (multiple users sharing a common system prompt), not per-session state fidelity for long-running individual sessions; it does not model session-specific history growth, multiple semantic fidelities, or mobility-induced candidate-set changes.

---

#### iv-B. QKVShare: Quantized KV-Cache Handoff for Multi-Agent On-Device LLMs

**(a)** Pratik Honavar, Tejpratap GVSL. "QKVShare: Quantized KV-Cache Handoff for Multi-Agent On-Device LLMs." arXiv:2605.03884, May 2026.

**(b)** QKVShare enables KV cache transfer between agents running on the same or nearby edge devices by quantizing the KV cache at mixed precision (Q4/Q8/FP16 per token based on importance) before transfer, packaging it as a self-contained CacheCard that can be injected into a HuggingFace model. It targets multi-agent workflows on edge devices where re-prefilling is too slow.

**(c)** QKVShare moves KV state across agent boundaries at the edge with reduced transfer cost, which is in the same design space as our KV-as-materialized-state transfer across mobile candidate nodes.

**(d)** QKVShare transfers KV between co-located or nearby agents at quantized precision (same semantic fidelity, reduced byte cost); it does not represent multiple semantic fidelities of the same session, does not anticipate provisioning at future candidate nodes before handover, and is not designed for sessions that accumulate tens-of-thousands-of-token histories under workload-dependent fidelity requirements.

---
