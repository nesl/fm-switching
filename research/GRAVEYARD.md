# FM-switching — Graveyard

Closed datasets and directions. Each entry states what was tried, the failure mode, and
the evidence pointer. Do not reopen without a new argument that addresses the failure mode.

---

## Closed datasets

### OpenEQA — **CLOSED, REVERSIBLE**
**Failure mode:** **Episode frames not obtainable by any documented route; the only surviving
mirror cannot be verified against the published md5.** Not a judgement about the task class — an
availability failure, and the first entry here that an **administrative act would undo** rather
than new evidence.

**Status of each documented route, checked 2026-11-19:**
- **ScanNet subset** (1,079 questions, 89 scenes): blocked on the ScanNet **Terms of Use**, which
  must be filled out and sent from an institutional address to `scannet@googlegroups.com`
  (*"The data is released under the ScanNet Terms of Use"*, `github.com/ScanNet/ScanNet`). Blocked
  independently on disk: RGB-only extraction is **62 GB** against 51 GB free.
- **HM3D Option 2** (render from Habitat): the trajectory-states archive
  `open-eqa-hm3d-states-v0.tgz` has **expired**; the re-upload request is still open
  (`github.com/kaist-ami/SplatReasoner/issues/1`).
- **HM3D Option 1** (pre-rendered frames, `open-eqa-hm3d-frames-v0.tgz`, published md5
  `286aa5d2fda99f4ed1567ae212998370`): **link expired**, verified directly. Same expiry reported
  independently (`github.com/intcomp/SegPruner/issues/1`, filed ~209 days before this check).
- **Surviving mirror** (`huggingface.co/datasets/AIGeeksGroup/OpenEQA`, MIT): carries the HM3D
  frames as **63 per-scene `.tar` files**. The published md5 covers a **single `.tgz` that no
  longer exists in that form**, so the checksum cannot be applied to it; the party that pinned the
  mirror states the original byte identity is **unverified**.

**Why the closure is clean rather than speculative.** The download was attempted. **`curl` exited
0 and wrote a file with the correct name**; the file was **230 KB of HTML** whose `<title>` is
**"Dropbox - Link Expired"**, md5 `2e5a0bda…` against the published `286aa5d2…`. A success signal
that was not one. **Without the requirement to verify the md5 rather than record it, that file
would have reached extraction or, worse, a result.** Three URL variants confirmed the expiry
(`dl=1` and `dl=0` both HTTP 200 `text/html`; `dl.dropboxusercontent.com` HTTP 403).

**REVERSIBLE:** if the ScanNet Terms of Use are signed and ~70 GB of disk is freed, the ScanNet
subset becomes available and **verifiable**, and this entry should be reopened. The annotations
were never the problem — they remain available under MIT.

**Evidence:** `reports/study_oeqa.md`.


### EgoLife
**Failure mode:** No accessible QA benchmark that isolates context compression as the
failure mode. Egocentric video + life-log, but the evaluation setup requires dense
annotation not available in the public release.

**Re-checked 2026-11-19 for D139 (questions that need history), StudyEGOLIFE-feas, annotation
only, no video. STAYS CLOSED, on a new and quantified ground.** The failure mode above was
answering a different question (context compression) and is left standing as written. For D139 the
**usable count is 3**: of the 500 published rows, 281 are same-day single-target, and applying
gap > 2 min, D2 history <= 19,400 tokens, no `need_audio` and no `need_name` leaves 281 -> 20 -> 15
-> 3. Against a threshold of 50 that is **offline corroboration only, not a trace-driven workload**,
and the margin is not close: 4 if every excluded multi-target row were repaired most favourably, 5
at a 32,768 budget. **`need_name` binds, not the token budget** - 197 of 281 need identity
recognition and only 34 of 281 need neither audio nor names.

Three further facts, for whoever looks next. **Licence is clear**: `lmms-lab/EgoLife` rev
`143fb319` is MIT and ungated. **The QA is 1 of 6 participants**, 500 of the paper's 3,000
questions, absent from GitHub too, while `EgoLifeCap/` dense captions and transcripts ARE public for
all six. **Recurring failure mode 2 below is AGGRAVATED, not merely untested: that caption layer is
Chinese-only** while the QA carries parallel English, which is the FindingDory failure exactly.
Also: EgoLifeQA is a multi-hour benchmark, 207 of 281 gaps beyond 30 min, and over all 500 rows the
median question would need 951,241 D2 tokens, 49x our budget.
Report `reports/study_egolife_feas.md`; counts `results/datasets/egolife_feas.json`.

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
