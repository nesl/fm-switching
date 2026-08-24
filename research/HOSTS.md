# FM-switching — Host Claims

Use this file to claim a GPU/host before running a long experiment, so concurrent sessions
don't collide. Clear the claim when done.

| host | GPU | claimed by | experiment | claimed at | status |
|---|---|---|---|---|---|
| flash | A6000 (GPU 1) | CC | E27 maintenance-mechanism kill test | 2026-08-20 | done |
| flash | A6000 (GPU 1) | CC | E29 tier-heterogeneous fidelity audit | 2026-08-21 | done |
| flash | A6000 (GPU 1) | CC | E26 vLLM calibration follow-up (warm append + YaRN) | 2026-08-21 | done |
| flash | A6000 (GPU 1) | CC | E32 staleness cost (quality HF + catch-up latency vLLM) | 2026-08-22 | done |
| flash | A6000 (GPU 1) | CC | E34 maintenance semantics + corrected catch-up latency | 2026-08-23 | done |
| flash | A6000 (GPU 1) | CC | E35 corrected WARM catch-up latency + maintenance ordering | 2026-08-23 | done |
| flash | CPU (no GPU) | CC | E36 maintenance-aware fleet admission simulation | 2026-08-23 | in-progress |
