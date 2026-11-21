# Host tier under policy control: what vLLM can actually do, and the smallest build that gives the policy

Session D (flash / A6000), 2026-11-21 ~13:30. **Design and feasibility only. Nothing deployed,
nothing run, no server touched.** D56 makes the tier a policy decision; D150 deferred an external KV
store as a later extension; the user now requires it.

## REGISTER FIRST, because it changes how much weight this carries

**This is from DOCUMENTATION, not from reading vLLM 0.31.0 source.** The box I am on has vLLM
**0.8.5**; the live2 server runs **0.31.0** and lives on the H100. I have asked the H100 for a
read-only grep of its installed package (connector classes, save/load/delete methods, per-request
cache fields, serve flags) and **that answer supersedes this document where they disagree.** Marked
**DOC** below where the claim rests on documentation alone.

## 1. Can the coordinator explicitly save, reload and delete a session's KV?

**No, not through any shipped API.** Three separate answers:

| operation | available? | what exists instead |
|---|---|---|
| **save to host** | **no explicit call** | `save_kv_layer` is an **internal hook called from inside the attention layer**, abstract on the connector base class, which starts an async copy of a layer's paged KV out to the connector. It is a side effect of serving a request, not something a coordinator invokes. **DOC** |
| **reload on demand** | **no explicit call** | reload happens **transparently on lookup**, when a prefix is requested again. The trigger is therefore **sending a request**, which is the actuator we already have. **DOC** |
| **delete / free** | **not available** | the only explicit delete I found is in an **RFC for a cross-engine KV cache service** (issue #14724), not in the shipped API. Treat as a proposal. **DOC** |

**What IS shipped:** a native `OffloadingConnector` providing asynchronous CPU offload over CUDA
DMA, from **v0.11.0** onward, so 0.31.0 has it. Configured with
`KVTransferConfig(kv_connector="OffloadingConnector", kv_role="kv_both")` for store and load, or on
the CLI as `--kv_offloading_backend native --kv_offloading_size <GB>`. A simpler
`SimpleCPUOffloadConnector` also exists, documented as **best effort**: "a dropped save is simply a
future cache miss". **DOC**

**So the tier becomes an economic fact, not a policy lever.** Offloading changes what a GPU miss
COSTS, from a full recompute to a host reload. It does not let a policy choose which session sits
where. That is a different thing from what D56 asks for.

**This is very likely why the host tier was never built.** `cstate.py:432` recorded the reason at
the time in one line, "Residency cannot be COMMANDED in vLLM (D44)", and the API position has not
changed in the direction D56 needs.

## 2. Can a request be excluded from caching or offload?

**No, not per request.** **DOC**

| | |
|---|---|
| prefix caching on/off | a **global server flag** (`--no-enable-prefix-caching`), not a per-request field |
| `cache_salt` | **partitions** the cache. Requests with different salts cannot share blocks. It is isolation, documented as opt-in and not passed by default. **It does not exclude a request from caching.** |
| `kv_transfer_params` | I did not establish any link to cache exclusion; it belongs to disaggregated serving. Unresolved, and on the H100's grep list. |

## 3. The smallest build that gives the POLICY, which does not need a tier API

The three aims are **robot history stays host-warm and is reloaded on demand**, **dashcam episode
dropped at episode end**, **single-shot never retained**. Taking the API as it is rather than as D56
wishes it were, two of the three are achievable with machinery this project ALREADY uses, and the
third is one server flag.

| aim | smallest mechanism | status today |
|---|---|---|
| robot history **host-warm, reloaded on demand** | enable `OffloadingConnector` with a sized host pool, and keep the session in the offload tier's LRU with a **TOUCH** request | connector: **one serve flag**. TOUCH: already 32B-confirmed (M2), not yet wired as a keep-warm action, which is item 3 |
| dashcam episode **dropped at episode end** | **roll the `cache_salt` at episode end.** The old episode's blocks become unreachable and age out; nothing can reuse them | **already expressible.** `cache_salt` is in every body (`bodies.py:168`), set per D84 |
| single-shot **never retained** | **a unique `cache_salt` per single-shot request**, so its blocks can never be shared with anything | **already expressible, and arguably already true**, since SS payloads are unique |

**The reframing that matters: the policy does not need save, reload and delete. It needs salt
lifecycle management, an offload tier, and TOUCH.** "Drop at episode end" becomes "make it
unreachable", which is what the policy actually wants, since the aim is that a stale episode never
serves a later request. Memory is not freed on the instant; it ages out under LRU. That is a
weaker guarantee than `delete` and it is the strongest one available.

### What it costs

| | |
|---|---|
| **a server restart** | enabling the connector needs one, and **this is the expensive part**: it breaks comparability with every cell already run, which `results/audit/comparability_ledger.json` exists to track. It cannot be slipped in mid-sweep. |
| host memory | `--kv_offloading_size` in GB. The harness already models `host_tier_gib = 27.0` and `host_tier_tokens = 110630`, so there is a declared target to match |
| offload bandwidth | async CUDA DMA, off the critical path by design, but it competes for PCIe with image uploads |
| policy code | small. A salt-rolling rule per device type, plus TOUCH as a keep-warm action |

### What it would change about the measurements

**Every "cold" in every committed result would become "host reload" instead of "recompute".** The
prefix-cache-miss finding from this morning is the clearest example: v5-rules-2's 139 cold prefills
at 5,480 uncached tokens each would instead be host reloads at whatever DMA costs. That is a
different experiment, not a better version of the current one, which is a reason to treat it as a
new arm family and not as a fix to the existing cells.

## 4. What I am NOT claiming

- I have **not** verified any of the API surface against 0.31.0 source. The H100's grep decides it.
- I have **not** measured offload bandwidth or reload latency on this hardware, so the economics
  above are qualitative.
- Whether `OffloadingConnector` in 0.31.0 exposes anything more explicit than the base hook is
  **open**. If it does, the picture improves and the answer to section 1 changes.
- **Nothing here is a recommendation to deploy.** The user has said design only, and a restart
  mid-measurement is exactly the kind of change the comparability ledger exists to prevent.

## Sources

- [vLLM KV connector v1 API index](https://docs.vllm.ai/en/latest/api/vllm/distributed/kv_transfer/kv_connector/v1/index.html)
- [`simple_cpu_offload_connector`](https://docs.vllm.ai/en/stable/api/vllm/distributed/kv_transfer/kv_connector/v1/simple_cpu_offload_connector/)
- [Inside vLLM's New KV Offloading Connector](https://vllm-project.github.io/2026/01/08/kv-offloading-connector.html)
- [KV Cache CPU Offload Guide (vllm-ascend)](https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/kv_cache_cpu_offload.html)
- [RFC: KV Cache Offloading for Cross-Engine KV Reuse (#14724)](https://github.com/vllm-project/vllm/issues/14724)
- [RFC: KV cache offloading (#19854)](https://github.com/vllm-project/vllm/issues/19854)
- [RFC: Cache Salting for Secure and Flexible Prefix Caching (#16016)](https://github.com/vllm-project/vllm/issues/16016)
- [vLLM security docs, `cache_salt` scope](https://docs.vllm.ai/en/stable/usage/security/)
- [`vllm.config.cache`](https://docs.vllm.ai/en/stable/api/vllm/config/cache/)
