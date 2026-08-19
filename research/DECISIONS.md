# FM-switching — Decision Log

Entries are newest first. Include the date, the decision, the reason, and the evidence
or conversation that settled it. Decisions here are final unless explicitly reopened.

---

## 2026-08-19 — Phase 1 gate passed (pending Jetson)

Physical inertia crossovers confirmed on two tiers (A6000, RTX 3090 Ti).
The summary-update bug (8000-char cap making update latency appear constant at ~2.6s)
was corrected; corrected xB shifts from ~16K to ~65K on A6000 and to none-in-range on
3090Ti (update OOMs above 32K). Gate passed on the A6000 tier; Jetson pending.
Implication: the summary pipeline is only cheaper than full re-prefill at very large L
(>64K tokens), not at moderate L as originally estimated.

---

## 2026-08-16 — Phase 0a gate passed (LoCoMo held under Mistral-7B)

The dense-incompressible result on LoCoMo (n=100) holds under Mistral-7B-Instruct-v0.2
with a gap matching the Qwen2.5-7B result. Infini-THOR under Mistral shows full>>summary
at the all-pool level (gap +0.140, p=0.033) but the model is near floor, making this
tentative (C2). Gate passed: regime taxonomy is not a model artifact for the primary
(LoCoMo) claim. The three Infini-THOR truncated items (73K+ token trajectories) are
permanently excluded (n=57) because the full condition is irrecoverable: CUDA OOM on
A6000 under Qwen, context_exceeded under Mistral.

---

## 2026-08-15 — Oracle regime labels allowed in first simulator only

The first simulator pass may use oracle regime labels (known workload type) as an upper
bound to establish that joint policy is possible in principle. A regime estimator must
follow before the result is submitted. Rationale: establishing the upper bound first is
standard practice; the estimator design is a separate contribution.

---

## 2026-08-10 — KV cache dropped from implemented representation set

KV cache was not implemented as a first-class representation in Phase 1 profiling.
Rationale: KV cache residency (56 KB/token for Qwen2.5-7B) makes transfer infeasible
on any realistic link (3.7 GB at 64K tokens). KV size and derived transfer cost are
reported in `cost_matrix.csv` as data, not as a candidate representation. If a future
boxed-context design changes the KV footprint by ≥10×, reconsider.

---

## 2026-08-08 — Agent is the CPS object; datasets supply semantic and physical dynamics

The paper's subject is the mobile FM agent, not any particular dataset. The
characterization workloads (EgoSchema, Infini-THOR, LoCoMo) supply semantic dependency
structure. Mobility traces (GeoLife, KITTI, or synthetic) supply physical dynamics for
the simulator. These are instrumentation, not the object of study. Consequence: adding
a new dataset requires a clear argument for which axis it covers that existing datasets
do not.

---

## 2026-08-05 — GeoLife double verdict resolved: archived

GeoLife passed the micro-gate for incompressibility (full=58.5%, s80=22.0%, gap
+36.6pp, p<0.0001). However, the question family (sequential recall: "what came before
X?") is lookup-type with guessable priors, and the gap may reflect the model's inability
to enumerate ordered sequences rather than compression-induced omission. The dataset is
archived. GeoLife mobility traces (GPS coordinates) remain available as physical dynamics
input to the simulator.

Evidence: `results/archive/geolife_microgate_qwen7b.json`.

---

## 2026-07-28 — Dataset hunt closed

After checking EgoLife, SuperMemory-VQA, NaVQA/ReMEmbR, FindingDory, GeoLife, Oxford
RobotCar, sensor-stream time series (OhioT1DM, PMData, T1DEXI, LifeSnaps), and
NarrativeQA, the dataset hunt is closed. The structural reason: datasets with coded or
templated logs (Infini-THOR, GeoLife GPS) summarize to a few tokens and fall in the
structured-compressible regime. Datasets with heterogeneous free-form narrative
(NarrativeQA, book/script corpora) move the paper away from CPS and duplicate LoCoMo's
role. The three-regime taxonomy (gist-compressible, structured-compressible,
dense-incompressible) is sufficient for the paper's claim.

---

## 2026-07-20 — NarrativeQA and book/script corpora rejected

NarrativeQA and similar book or script corpora would duplicate LoCoMo's dense-incompressible
role while moving the paper's setting away from cyber-physical systems. Rejected.

---

## 2026-07-10 — Oxford RobotCar and sensor-stream feasibility checks: informative, not used

Oxford RobotCar AV logs feasibility check (`reports/oxford_av_feasibility.md`): context
sizes 6–40K tokens; no QA benchmark that isolates compression as failure mode. Informative
for C3 (structured logs), but insufficient for a characterization claim. Archived.

Sensor-stream feasibility check (`reports/sensor_stream_feasibility.md`): medical time
series (OhioT1DM, PMData, T1DEXI, LifeSnaps) produce 0.5–2K token contexts — small
enough that full-replay is always feasible; no incompressibility pressure. Archived.

---

## 2026-06-20 — SSM+MPC+RL control-plane direction superseded

The March 2026 SSM+MPC+RL direction (latency-hiding policies, speculative prefill, GRU
routing) is superseded by the representation-aware framing. Code is kept in `simulator/`
for lineage and for the LH-variant Pareto analysis (which showed Speculative = RoutedSync
by construction, softening the original Pareto claim). No further development in this
direction.

---

## 2026-06-15 — FindingDory closed (perception failure, not compression failure)

FindingDory-captions fails at perception: the fine-tuned QwenVL-3B model is OOD above
b=48 frames (trained only on b=96), and subsampled active-object captions lose reference
anchors so full ≈ summary ≈ blind. The failure mode is captions discarding spatial
anchors, not the summarizer discarding facts. Closed as a negative result.

Evidence: `results/archive/fd_captions_qwenvl7b.json`, `results/archive/fd_pilot_v2_qwen7b.json`,
memory file `findingdory_negative.md`.
