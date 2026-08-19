# FM-switching — Graveyard

Closed datasets and directions. Each entry states what was tried, the failure mode, and
the evidence pointer. Do not reopen without a new argument that addresses the failure mode.

---

## Closed datasets

### EgoLife
**Failure mode:** No accessible QA benchmark that isolates context compression as the
failure mode. Egocentric video + life-log, but the evaluation setup requires dense
annotation not available in the public release.

### SuperMemory-VQA
**Failure mode:** The benchmark tests retrieval from a structured memory store, not
from a compressed context representation. The failure mode when compression is applied
is retrieval miss, not reasoning failure — conflates two phenomena.

### NaVQA / ReMEmbR
**Failure mode:** Embodied navigation QA; spatial reasoning over 3D maps. The compression
signal is confounded with spatial layout encoding, not semantic history compression.
Moving too far from the CPS session-state framing.

### FindingDory
**Failure mode:** Perception failure, not compression failure.
The fine-tuned QwenVL-3B model is out-of-distribution above b=48 frames (trained only
on b=96). Subsampled active-object captions lose spatial reference anchors, making
full ≈ summary ≈ blind — the comparison collapses before compression is even tested.
Evidence: `results/archive/fd_captions_qwenvl7b.json`,
`results/archive/fd_pilot_v2_qwen7b.json`, `reports/` (negative, not filed separately).

### GeoLife (as QA benchmark)
**Failure mode:** Question family is lookup-type with guessable priors.
The micro-gate passed (full=58.5%, s80=22.0%, gap +36.6pp), but sequential-recall
questions ("what came before X?") test whether the model can enumerate ordered sequences,
which depends on tokenized representation of ordering, not on whether the gold entity
was omitted by the summarizer. Cannot disentangle compression-omission from ordering-encoding
failure. GeoLife GPS coordinates remain usable as physical dynamics input to the simulator.
Evidence: `results/archive/geolife_microgate_qwen7b.json`.

### Oxford RobotCar (AV logs)
**Failure mode:** No QA benchmark that isolates compression as failure mode.
Context sizes 6–40K tokens (feasible). Structured log format (likely structured-compressible
per C3) but no evaluation set. Logged in `reports/oxford_av_feasibility.md`.

### OhioT1DM / PMData / T1DEXI / LifeSnaps (sensor-stream time series)
**Failure mode:** Context sizes too small (0.5–2K tokens) for incompressibility pressure.
At these lengths, full-replay is always computationally feasible (restore < 300 ms even
on Jetson). No compression pressure → no interesting crossover. Logged in
`reports/sensor_stream_feasibility.md`.

### NarrativeQA and book/script corpora
**Failure mode:** Wrong domain. Book/script corpora move the paper away from cyber-physical
systems and duplicate LoCoMo's dense-incompressible role. The paper's setting is mobile
FM agents in CPS, not literary comprehension.

---

## Closed directions

### March 2026 SSM+MPC+RL control-plane (latency-hiding policies)
**Superseded by:** representation-aware framing (current).
The latency-hiding approach treated context compression as a fixed given and optimized
network-aware prefill scheduling. The representation-aware framing shows that the
choice of representation (what state to hold) is the primary decision variable, with
latency hiding as a downstream effect. The Pareto analysis of LH variants was also
weakened: SpeculativeLH and RoutedSyncLH return byte-exact identical results because
RoutedSync uses ground-truth instantaneous RTT (same information as Speculative's
post-hoc oracle). Code kept in `simulator/` for lineage.

---

## Recurring failure modes

1. **No QA benchmark isolating compression**: most AV, robotics, and IoT datasets lack
   evaluation sets designed to test whether a specific piece of information survives
   summarization. Feasibility checks can be done quickly; benchmark development is
   out of scope.

2. **Perception failure before compression is tested**: captioning-pipeline datasets
   (FindingDory, EgoLife) require a working perception layer. If the captioner degrades
   at reduced frame budgets, the compression signal is confounded.

3. **Question family with guessable priors**: lookup-type questions (GeoLife sequential
   recall, some NaVQA spatial questions) allow models to guess from priors, making
   blind > 0. The gap full − summary can still be real but the mechanism cannot be
   attributed to compression omission.

4. **Context too small**: sensor-stream datasets with <2K token contexts show no
   incompressibility pressure because full-replay is always cheap. The interesting
   regime is L > 8K where the cost crossovers (xC, xB) become relevant.
