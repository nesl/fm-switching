# FM-switching — Host Claims

Use this file to claim a GPU/host before running a long experiment, so concurrent sessions
don't collide. Clear the claim when done.

Shared H100 host (`sn4622120321`): read `research/HOST_H100.md` first — use GPU 3 by default.

| host | GPU | claimed by | experiment | claimed at | status |
|---|---|---|---|---|---|
| flash | A6000 (GPU 1) | CC | E27 maintenance-mechanism kill test | 2026-08-20 | done |
| flash | A6000 (GPU 1) | CC | E29 tier-heterogeneous fidelity audit | 2026-08-21 | done |
| flash | A6000 (GPU 1) | CC | E26 vLLM calibration follow-up (warm append + YaRN) | 2026-08-21 | done |
| flash | A6000 (GPU 1) | CC | E32 staleness cost (quality HF + catch-up latency vLLM) | 2026-08-22 | done |
| flash | A6000 (GPU 1) | CC | E34 maintenance semantics + corrected catch-up latency | 2026-08-23 | done |
| flash | A6000 (GPU 1) | CC | E35 corrected WARM catch-up latency + maintenance ordering | 2026-08-23 | done |
| flash | CPU (no GPU) | CC | E36 maintenance-aware fleet admission simulation | 2026-08-23 | done |
| flash | CPU (no GPU) | CC | E36b fleet simulation with measured A1 ratio | 2026-08-24 | done |
| flash | CPU (no GPU) | CC | E36b rewrite — corrected fleet policy (footprint_ranked incumbent, admissibility model) | 2026-08-24 | done |
| flash | CPU (no GPU) | CC | E36c — fleet policy with fixed KV capacity and fleet-level knapsack maintenance_aware | 2026-08-24 | done |
| jetson_orin | Orin (65.9 GB unified) | CC | E37 qwen3b vs qwen7b device-tier time ratio | 2026-08-23 | done |
| sn4622120321 | H100 NVL (GPU 2 for arm C + first D trials; GPU 3 from 19:20, dedicated ~16 h) | CC | H100 night run: StudyR → StudyS2 → StudyT (bf16) | 2026-10-14 | done (2026-10-15 08:16) |
| sn4622120321 | H100 NVL (GPU 3) | CC | Flash-attn 32B re-run: StudyT long-trace VRAM, StudyR/S2/T 32B arms (no time limit; halts on any foreign GPU-3 process) | 2026-10-15 | done (2026-10-16 02:56; 0 foreign processes) |
