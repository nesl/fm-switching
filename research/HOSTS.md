# FM-switching — Host Claims

Use this file to claim a GPU/host before running a long experiment, so concurrent sessions
don't collide. Clear the claim when done.

Shared H100 host (`sn4622120321`): read `research/HOST_H100.md` first — use GPU 3 by default.

---

## Runtime-estimate rule (added 2026-10-16, mandatory)

**Any runtime estimate must state the assumed median generation length and the study it was
extrapolated from.** A latency figure carried without its token count is not transferable.

Write estimates in this form:

> StudyO Q4 4B-T cell: ~2.8 h for 845 trials — 11.8 s/trial mean, median 327 generated tokens,
> measured on 10 trials of this cell (not extrapolated).

Not: *"~25 h, based on StudyP's 4B-Thinking."*

**Why.** Three errors in one session came from moving a latency number between workloads with
different generation lengths:

| error | wrong | actual | cause |
|---|---|---|---|
| StudyO Q4 sizing | 15–25 h | **2.4–3.9 h** | extrapolated from StudyP at 104 s/trial (8,192-token budget, long reasoning); S-EMBER terminates at a median of 327 tokens, 0/10 hitting the cap |
| StudyJ6 projection | 6.1–7.0 h | ~6 h, after swinging 4.5–7.7 h | projected from the cap-hit stratum, selected for being the slowest signs, then over-corrected off two trivial ones |
| "flash-attn is slower on short generations" | −23 to −35% | never slower, 1.00–2.26× | bucketed raw latency by one backend's token counts on sampled arms, where the other backend re-draws a different length |

The same failure underlies all three: **a per-trial latency is a function of tokens generated,
and tokens generated is a property of the workload, not the hardware.** Two numbers may be
compared only when their generation lengths are stated and comparable.

Corollaries:

- Projecting from a **selected subgroup** estimates that subgroup, not the population. Say which
  stratum the sample came from.
- A **throughput** (tok/s) figure transfers between workloads; a **latency** figure does not.
  Prefer tok/s when extrapolating, then multiply by the target's expected token count.
- State a band. A 10-trial sample whose max is 2x its median has not seen the tail; ±30% is a
  reasonable default until the real run lands.

See `reports/cost_ratio_basis.md` for the related rule on mean-vs-median cost ratios, and
`reports/multiplier_provenance_audit.md` for the provenance requirement on quoted multipliers.

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
