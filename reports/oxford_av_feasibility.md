# Oxford RobotCar / Radar RobotCar — Feasibility Report

**Question:** Is Oxford RobotCar suitable as a long-horizon dense-recall incompressibility QA workload?

**Verdict up front:** **NO-GO as QA workload. GO-AS-SUBSTRATE-ONLY.**

---

## Section 1 — Inventory

### Oxford RobotCar Dataset

**Source:** https://robotcar-dataset.robots.ox.ac.uk/

| Property | Value |
|---|---|
| Traversals | 100+ |
| Date span | May 2014 – November 2015 (~18 months) |
| Route | Fixed 10 km loop through central Oxford, UK |
| Per-traversal duration | ~15–20 min (chunked into ~6-min segments) |
| Total dataset size | >20 TB |
| Per-traversal download | 10 GB (short/partial) – 427 GB (full traversals with all sensors) |

**Sensors per traversal (raw data released):**

| Sensor | Spec | Rate |
|---|---|---|
| Bumblebee XB3 trinocular stereo camera | 1280×960, 3 lenses | 16 Hz |
| 3× Grasshopper2 monocular cameras | 1024×1024 | 11.1 Hz |
| 2× SICK LMS-151 2D LiDAR | 270° FoV, 50 m range | 50 Hz |
| SICK LD-MRS 3D LiDAR | 85° HFoV, 4 planes | 12.5 Hz |
| NovAtel SPAN-CPT GPS/INS | 6-axis | 50 Hz |

No radar in the base dataset. The **Radar RobotCar** extension (32 traversals, January 2019, 280 km total, 4.7 TB) adds a Navtech CTS350-X FMCW scanning radar and upgrades to 2× Velodyne HDL-32E LiDAR, keeping the same camera and GPS/INS stack.

**License and access:**
- Creative Commons Attribution-NonCommercial-ShareAlike 4.0 (CC BY-NC-SA 4.0)
- Registration required to download; registration appears to process in batches (the dataset page showed a notice pausing new requests as of July 2026)
- Commercial use requires contacting Oxford directly
- Not trivially redistributable

**Annotations released:**

The dataset ships a `tags.csv` per traversal with coarse condition labels:
`sun | clouds | overcast | rain | snow | night | dusk | roadworks | detour | alternate-route | poor-gps | no-gps | short | partial`

No pixel-level semantic segmentation, no object bounding boxes, no per-frame captions, no place recognition splits are shipped with the raw dataset (place recognition splits are defined per-paper by researchers and not standardized).

RTK ground truth poses are available as a separate download ([arxiv 2002.10152](https://arxiv.org/pdf/2002.10152)).

**Existing QA/captioning/language derivatives:** None found. Search for "Oxford RobotCar QA", "Oxford RobotCar captioning", "Oxford RobotCar natural language" returns no relevant derivatives. The dataset is used exclusively for localization, place recognition, SLAM, and domain adaptation — not for language-grounded tasks.

---

## Section 2 — Anchor Recoverability

### What perception is cheaply producible

| Output | Source | Feasibility |
|---|---|---|
| Vehicle/pedestrian/cyclist detection | Off-the-shelf detector (YOLO, DETIC) on mono/stereo frames | Straightforward |
| Traffic light state (red/green) | Detector + classifier | Feasible but noisy |
| GPS → OSM place label | Nominatim/Overpass on GPS trace | Feasible; UK urban OSM coverage is good (unlike Beijing) |
| Weather condition | Image-based classifier | Feasible; also available from tags.csv |
| Roadworks zone detection | Detector (construction vehicle, barrier, cone) | Uncertain reliability — rare class, YOLO-class detectors perform poorly on construction specifics |
| Fog / heavy rain visibility | Image statistics or classifier | Feasible |

### Anchor survival analysis

**The critical risk is not perception failure — it is structural predictability.**

The Oxford RobotCar route is a **fixed 10 km loop** traversed 100+ times. This creates a spatial prior: every traversal passes through the same junctions, the same bridge, the same pedestrian crossings, the same sections where roadworks historically occurred. Rare events like "construction zone" do not appear at random positions in the log — they appear **at the same GPS coordinates across traversals** because the route is fixed and the roadworks at a given location persisted for weeks or months.

This means:
- A per-timestep observation log for any traversal has the form: `[timestamp, GPS, objects_detected, weather_state]`
- The spatial structure (which intersection, which road segment) is the same across all traversals
- The log is therefore highly **spatially templated**: the sequence of locations is identical for every traversal

A typical 15-min traversal at 1 observation per 10 seconds yields ~90 entries. At 30 tokens each that is ~2,700 tokens per traversal — in the Infini-THOR range (873–2149 tokens). At 1 obs/sec it is 27,000 tokens, but at that density it is unreadable noise.

**Observation diversity:** Within a single traversal, observations vary only in: traffic density, pedestrian count, weather, and whether a particular zone has active construction. The sequence of road segments is invariant. This is low diversity — closer to 5–10 stereotyped templates per segment than the open-ended variation of conversational memory.

**Rare-event anchor fate:**
- "Roadworks" is a tag in tags.csv — it already summarizes to one bit. A summary would say "roadworks present" and that is sufficient to answer most queries about it.
- "Rain" similarly collapses to a binary per traversal.
- "Construction vehicle at junction X" could in principle be a specific anchor — but since junction X is always the same location (fixed route), this is predictable from the route structure.

**Comparison to prior failures:**
- FindingDory: anchors lost at perception subsampling stage. Oxford RobotCar avoids this: objects would survive in the log. ✓
- Infini-THOR: structured-log compression — summaries captured all relevant events. Oxford RobotCar is at high risk of this failure because: (a) the route is fixed, (b) condition tags already form a natural 1-line summary, (c) rare events are spatially predictable. ✗

---

## Section 3 — Query Family Design

### Candidate Q1: Last-occurrence (within-traversal)

**Template:** "In traversal X, at what timestamp did the vehicle last encounter a construction barrier?"

**Evidence required:** Detection of construction barriers in the perception log; the last occurrence timestamp.

**Guessability risk:** HIGH. Construction barriers appear at the same GPS coordinates across all traversals (fixed route). A model with route knowledge can say "construction was near the Banbury Road section" without reading the log. The blind baseline would not be zero.

**Mitigation attempt:** Restrict to events whose location varies (e.g., a parked delivery vehicle, a pedestrian group). But these are individually rare and the perception pipeline would need to reliably distinguish "delivery vehicle" from "car" — uncertain.

**Assessment:** Borderline. Spatial predictability partly undermines non-saliency.

### Candidate Q2: Count-over-window (cross-traversal)

**Template:** "How many of the 10 traversals in March 2015 included at least one pedestrian crossing event?"

**Evidence required:** Detection of pedestrian crossing events across 10 traversals; requires sweeping all 10 logs.

**Guessability risk:** MEDIUM. Pedestrian crossings at specific junctions on the fixed route are highly predictable. Every traversal passes the same crossings. The prior is "pedestrian crossings occur at crossing X, Y, Z; their presence depends on time of day." A blind baseline aware of the route would score non-trivially.

**Mitigation attempt:** Use very specific anchor (e.g., "group of more than 5 pedestrians at a single crossing"). But reliable counting at that specificity from off-the-shelf detection is uncertain.

**Assessment:** Weak. Cross-traversal counting is genuinely long-horizon (sweeps multiple traversal logs), but the fixed route undermines non-saliency.

### Candidate Q3: Cross-traversal comparison (condition-based)

**Template:** "Of traversals A, B, C (dates given), which had the highest number of red traffic light stops?"

**Evidence required:** Traffic light state across full traversal logs; ordering of traversals by count.

**Guessability risk:** MEDIUM-LOW. Traffic light patterns depend on time of day and traffic, not fixed route alone. A blind baseline cannot reliably rank traversals by red-light stops. This is the strongest candidate.

**Mitigation attempt:** Exclude traversals that differ by time-of-day (which is predictable) — use traversals at the same time of day. Exclude the highest-traffic traversal from the anchor.

**Assessment:** Best of the three, but requires reliable traffic light detection across full traversals — a non-trivial perception requirement with commercially-calibrated models.

**Overall assessment of query families:** All three suffer from the fixed-route prior. Q3 (cross-traversal red-light comparison) is the strongest but depends on accurate traffic-state detection and does not fully avoid guessable priors.

---

## Section 4 — Regime Prediction

**Prediction: (A) Summary ≈ Full (Infini-THOR outcome). High confidence.**

Reasoning:

**Log length and structure.** At a practical subsampling rate (1 obs/10s), a 15-min traversal produces ~90 timestep observations. Each observation is something like: `"T=342s | Banbury Rd @ 51.7621°N,1.2573°W | cars:3 | pedestrians:1 | weather:rain | visibility:good"`. That is ~25–35 tokens. Total: ~2,700 tokens per traversal — squarely in the Infini-THOR range.

**What an 80-token summary captures.** A traversal with roadworks and rain would summarize naturally as: "Morning traversal, Overcast/rain. Roadworks active near junction at km 4.2. Moderate pedestrian and vehicle traffic. Total duration 17 min." That is ~40 tokens and captures the key distinguishing facts. An LLM reading this summary can answer: "Was there rain? Yes. Roadworks? Yes. Night? No." — the same answers as reading the full 2,700-token log.

**Why the fixed route breaks incompressibility.** The incompressibility mechanism in LoCoMo is that facts are sparse and non-repeated across a long heterogeneous context (10+ conversation sessions, diverse topics). In Oxford RobotCar, the facts repeat spatially: the vehicle always passes the same roads, the same crossings, the same junctions. The rare event (construction) appears in the same 200-meter section every traversal that has it. A summary that says "roadworks at section 4" is sufficient.

**The one escape hatch.** If queries required recovering exact timestamps or sub-minute ordering of rare events within a traversal ("did the pedestrian group appear before or after the red light at junction X?"), summaries might fail because temporal ordering is discarded by summaries. But this is a weak signal and would require very careful question design.

**Verdict:** Oxford RobotCar is a **structured, spatially-templated log** over a fixed route. The same failure mode as Infini-THOR applies. Summary will approximately equal full on any practically designable query family.

---

## Section 5 — Cost Estimate for 100-Question Pilot

| Item | Estimate |
|---|---|
| **Download volume** | 10 traversals × ~50 GB typical = ~500 GB. Radar RobotCar (32 traversals) is 4.7 TB total (~150 GB/traversal). Registration required; batch processing delays possible. |
| **Perception passes** | Object detection on camera frames: 15 min × 16 Hz × 10 traversals = ~144,000 frames. At ~50 ms/frame on A6000 = ~2 GPU-hours. Traffic light classification adds ~0.5 GPU-hours. Total: ~3 GPU-hours. |
| **Engineering: render pipeline** | Build GPS→OSM labeler, camera→detection→text serializer, per-traversal log builder: **3–4 engineering days** |
| **Engineering: author pipeline** | Template-based question authoring with non-saliency filtering: **1–2 days** |
| **Engineering: audit harness** | Reuse/adapt existing `geolife_audit.py` pattern: **1 day** |
| **Total engineering** | **5–7 days** |
| **Calendar estimate** | 2 weeks (including download delays, registration processing, iteration) |

If the regime test (Section 4) proves correct and summary ≈ full, this is 2 weeks spent to confirm a negative result.

---

## Final Recommendation

**NO-GO as QA incompressibility workload. GO-AS-SUBSTRATE-ONLY.**

Oxford RobotCar avoids the FindingDory failure (perception anchors would survive in the log) but walks directly into the Infini-THOR failure: the fixed 10 km Oxford route means every traversal's observation log is spatially templated over the same sequence of road segments, intersections, and landmarks. Condition variation (rain, roadworks, night) is already captured by the shipped `tags.csv` in one or two tokens per traversal. An 80-token LLM-generated summary would preserve these distinguishing facts, leaving no incompressibility gap for any practically designable query family. The counting and comparison query families (Q2, Q3) are partially redeemed by being cross-traversal, but the fixed-route prior means blind baselines will not fail cleanly, weakening the non-saliency requirement. The dataset has no language/QA derivatives, so all authoring must be built from scratch, making the engineering cost equivalent to LoCoMo while the predicted outcome is negative.

**As substrate:** The GPS traces, traversal timing, weather conditions, and sensor schedule make Oxford RobotCar useful for the FM-switching **simulator cost model** — specifically for calibrating mobility patterns, edge-sensor data rates, and context-size distributions for AV workloads. The Radar RobotCar's 32 traversals in January 2019 provide a clean, bounded dataset for this use. This value is independent of the QA outcome.

**Recommended next step:** Evaluate NarrativeQA (46K QA pairs over full books and movie scripts, 50K–100K token contexts, human-authored ordering/sequential questions) as the next QA workload candidate. It avoids all four prior failure modes: no perception stage, contexts are heterogeneous narratives (not fixed-route templates), facts are sparse and non-repeated, blind baseline is near zero for specific sequential questions.

---

*Sources consulted:*
- [Oxford RobotCar Dataset](https://robotcar-dataset.robots.ox.ac.uk/)
- [Oxford RobotCar Documentation](https://robotcar-dataset.robots.ox.ac.uk/documentation/)
- [Oxford RobotCar Datasets list](https://robotcar-dataset.robots.ox.ac.uk/datasets/)
- [Oxford Radar RobotCar Documentation](https://oxford-robotics-institute.github.io/radar-robotcar-dataset/documentation)
- [1 Year, 1000km: The Oxford RobotCar Dataset (IJRR 2017)](https://journals.sagepub.com/doi/abs/10.1177/0278364916679498)
- [Oxford Radar RobotCar Dataset paper (arxiv 1909.01300)](https://arxiv.org/pdf/1909.01300)
- [Real-time Kinematic Ground Truth (arxiv 2002.10152)](https://arxiv.org/pdf/2002.10152)
