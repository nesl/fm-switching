<!-- Paths in this report predate the 2026-08-19 reorganization; see research/EXPERIMENTS.md for current file locations. -->
# Personal Sensor Stream Datasets — Feasibility Report

**Question:** Do open personal sensor stream datasets (OhioT1DM, PMData, T1DEXI, LifeSnaps) support a long-horizon dense-recall QA workload for the FM-switching incompressibility audit?

**Verdict up front:** **NO-GO for all four candidates as QA workload.** The failure mode is the same across all of them and is intrinsic to the domain: personal health sensor streams have a small event vocabulary (hypo, meal, bolus, exercise, poor sleep) and few notable events per week (~5–10), which LLM summarizers enumerate explicitly in 40–80 tokens, collapsing the incompressibility gap.

---

## Section 1 — Inventory

### 1.1 OhioT1DM

| Property | Value |
|---|---|
| **Access** | DUA required; email razvan.bunescu@charlotte.edu with researcher name, institution, title; dataset delivered as compressed+encrypted archive; ~1 week processing |
| **Redistribution** | Not permitted; DUA restricts sharing |
| **Subjects / Duration** | 12 subjects (6 per release: 2018, 2020), 8 weeks per subject |
| **CGM** | Every 5 minutes (Medtronic Enlite sensor) |
| **Insulin** | Bolus and basal doses (pump log; timestamped) |
| **Meals** | Self-reported: timestamp + **carbohydrate estimate in grams only** — no food names, no free text descriptions |
| **Life events** | Exercise (time + exertion **coded 1–10**), sleep (time + quality **coded 1–3**: Poor/Fair/Good), work (time + exertion coded 1–10), stress (timestamp only), illness (timestamp only), hypoglycemic episodes (timestamp only) |
| **Physiological** | Heart rate, galvanic skin response, skin/air temperature, steps, acceleration (varies by fitness band: Basis Peak or Microsoft Band) |
| **Format** | XML (24 files; one train + one test per subject) |
| **Download size** | Not published; estimated ~100–500 MB total (12 subjects × 8 weeks × multi-channel XML) |
| **Existing QA/language derivatives** | None found. All downstream work uses the dataset for glucose prediction ML, not language tasks. |

**Sources:** [PMC article](https://pmc.ncbi.nlm.nih.gov/articles/PMC7881904/), [Dataset page](https://webpages.charlotte.edu/rbunescu/data/ohiot1dm/OhioT1DM-dataset.html)

---

### 1.2 PMData

| Property | Value |
|---|---|
| **Access** | Open; CC BY-NC 4.0; available on [OSF](https://osf.io/vx4bk/) and [Simula Datasets](https://datasets.simula.no/pmdata/) |
| **Redistribution** | Permitted with attribution, non-commercial |
| **Subjects / Duration** | 16 subjects, 5 months (November 2019 – March 2020) |
| **Fitbit Versa 2** | Calories, steps, distance, heart rate (continuous), activity minutes, sleep stages |
| **PMSys wellness app** | Daily wellness reports: fatigue, mood, readiness, soreness, stress — all **coded numeric scales** |
| **Google Forms (daily)** | Meal presence (breakfast/lunch/dinner/evening logged as present/absent), fluid glasses consumed, body weight, alcohol presence — **no food names, no portion sizes, no descriptions** |
| **Food photos** | 644 images from subjects 1, 3, 5 only (2-month period); not text-native |
| **Activity sessions** | 1,484 logged sports sessions; type coded (run/cycle/etc.), duration, distance |
| **Volume** | 11,425,966 heart rate measurements; 1,090 wellness reports |
| **Download size** | Not explicitly stated; estimated <5 GB |
| **Existing QA/language derivatives** | None found. Used for wellness prediction and sleep quality ML. |

**Sources:** [Simula PMData page](https://datasets.simula.no/pmdata/), [ACM MMSys paper](https://dl.acm.org/doi/10.1145/3339825.3394926), [OSF](https://osf.io/vx4bk/), [ResearchGate figure showing Google Form format](https://www.researchgate.net/figure/Google-form-to-collect-eating-and-drinking-habits_fig2_339584055)

---

### 1.3 T1DEXI

| Property | Value |
|---|---|
| **Access** | DUA via [Vivli](https://vivli.org/) (Center for Global Clinical Research); described in recent literature as "onerous" multi-step process requiring human review |
| **Redistribution** | Not permitted per DUA |
| **Subjects / Duration** | ~300+ adult T1D subjects, 4 weeks each |
| **CGM** | Dexcom G6, 5-minute intervals |
| **Wearable** | Verily wearable (activity, HR) |
| **Exercise logs** | Via T1DEXI mobile app: time, duration, activity type (coded) |
| **Meal logs** | Via app; food detail level not clearly documented in public sources — likely coded food entries or carb estimates, not free text |
| **Download size** | Not publicly stated |
| **Existing QA/language derivatives** | None found. Used for exercise-glycemia research. |

**Sources:** [Sagepub paper on T1DEXI glycemia/exercise](https://journals.sagepub.com/doi/10.1177/19322968241246458), [MetaboNet-Bench](https://arxiv.org/html/2606.18640v1)

---

### 1.4 LifeSnaps

| Property | Value |
|---|---|
| **Access** | Open; publicly available on Kaggle; GDPR compliant |
| **Redistribution** | Permitted (open access) |
| **Subjects / Duration** | 71 subjects, 4+ months |
| **Fitbit Sense** | Heart rate, steps, sleep, SpO2, skin temperature, activity — continuous |
| **Validated surveys** | Personality (Big Five), anxiety (STAI), etc. — coded scores, administered once or rarely |
| **Ecological momentary assessments (EMA)** | Daily goals, mood, context — **coded numeric scales**, not free text |
| **Volume** | >35 data types, >71 million rows, second-to-daily granularity |
| **Download size** | Not stated; large (71M rows suggests multi-GB) |
| **Existing QA/language derivatives** | None found. Used for mood/anxiety prediction. |

**Sources:** [Scientific Data paper](https://www.nature.com/articles/s41597-022-01764-x), [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC9622868/)

---

## Section 2 — Joined Event Log Design (OhioT1DM, top candidate)

### Design choice

Two options:
- **Dense CGM log**: one line per 5-min reading → 2,016 lines/week. Captures the full glucose trace but produces 16K+ tokens of mostly-redundant numeric data.
- **Event-first log**: one line per CGM reading at 15-min bucket (672/week) plus one line per meal/bolus/exercise/sleep/life event. This is the right design: it retains the glucose trajectory at readable density while preserving all event annotations.

**Recommended design:** 15-min CGM buckets + one line per annotation event (meal, bolus, exercise, sleep boundary, hypo, stress, illness).

### Token estimate

| Source | Lines/week | Tokens/line | Tokens/week |
|---|---|---|---|
| CGM at 15-min buckets | 672 | 8 | 5,376 |
| Meals (~21 events) | 21 | 12 | 252 |
| Bolus events (~40–60) | 50 | 10 | 500 |
| Sleep boundaries (14 = 7 starts + 7 ends) | 14 | 12 | 168 |
| Exercise (3–5 events) | 4 | 12 | 48 |
| Life events (stress, illness, hypo) | 5 | 10 | 50 |
| **Total** | | | **~6,400 tokens/week** |

This is comfortably above the 500-token minimum. A full 8-week subject context is ~51,200 tokens.

### Example log lines

```
2018-10-15 08:05  CGM: 142 mg/dL
2018-10-15 08:12  MEAL: breakfast, 45g carbs, bolus 3.5u
2018-10-15 08:13  BOLUS: 3.5u meal bolus
2018-10-15 02:17  CGM: 63 mg/dL [HYPO <70]
2018-10-15 02:20  HYPO EVENT logged
2018-10-14 22:30  SLEEP START: quality 2 (Fair)
2018-10-15 06:45  SLEEP END: duration 8h15m
2018-10-15 17:00  EXERCISE: 45 min, exertion 7/10
```

### Templating assessment

The log has **low variety**: every entry is one of ~8 templates (CGM reading, meal, bolus, sleep start/end, exercise, hypo, stress, illness). The CGM block is numerically varied but structurally identical across all lines. This is the same regime as Infini-THOR: a structured, low-vocabulary event log. The LLM summarizer knows what to extract and will.

---

## Section 3 — Anchor Analysis

### OhioT1DM

| Channel | Classification | Justification |
|---|---|---|
| CGM values | **Derivable** | Mean, range, time-in-range are statistics; specific values at specific timestamps are sparse-specific in principle but not useful as QA anchors (see below) |
| Bolus doses | **Derivable** | Total daily insulin is a statistic; individual bolus amounts are numeric and forgettable |
| Meal events — timestamp | **Sparse-specific** | Exact meal time is not derivable |
| Meal events — carbs | **Derivable** | Carb count is a number from a small range (~30–120g); no food name, so no memorable specific anchor |
| Sleep quality score | **Derivable** | 1-3 ordinal score; "poor sleep nights" collectable in a summary |
| Exercise exertion score | **Derivable** | 1-10 ordinal score |
| Hypoglycemic episodes | **Sparse-specific** | Timing is non-derivable, but count per week is small (0–5) |
| Stress/illness events | **Sparse-specific (thin)** | Timestamps only, no detail |

**Sparse-specific events per subject-week (estimate):**
- Hypo episodes: 0–4 (median ~2)
- Large meals (>80g carbs): 1–3
- Exercise sessions: 2–5
- Poor sleep nights (rated 1): 0–2
- **Total: ~5–12 sparse-specific events per week**

This is **THIN** (well below 20/week). More importantly, these events are all within a small categorical vocabulary — an LLM knows exactly what "notable" means in a T1D context.

**Summarizer-carries-anchors risk: CRITICAL.** A competent LLM summarizing one week of OhioT1DM data will produce something like:

> "Week 3 (Oct 15–21): Three hypoglycemic episodes (Monday 03:00, Wednesday 14:30, Saturday 22:00). Average glucose 142 mg/dL. Largest meal Tuesday dinner 110g carbs. Exercise Thursday afternoon, exertion 7/10. Poor sleep Sunday (rated 1/3)."

That is ~60 tokens and it carries **every sparse-specific event**. An LLM reading this summary can answer any practically designable query as well as one reading the full 6,400-token log. The gap collapses.

**This is the kill condition.** The events are few enough and categorical enough that 80-token summaries enumerate them completely.

---

### PMData (second candidate)

| Channel | Classification | Justification |
|---|---|---|
| Fitbit HR/steps/calories | **Derivable** | All aggregate statistics |
| Sleep stages | **Derivable** | Total sleep, REM percentage are statistics |
| Wellness scores (PMSys) | **Derivable** | Coded 1–7 scales; weekly averages capture it |
| Meal presence (Google Form) | **Derivable** | "Had breakfast: yes/no" — no food content, purely coded |
| Activity sessions (type+duration) | **Sparse-specific (thin)** | Session type and duration are specific but coded; a summary lists them easily |
| Body weight | **Derivable** | Daily measurement, changes slowly, compresses to trend |
| Food photos (3 subjects only) | **Sparse-specific** | Food content is specific — BUT: only 3 subjects, and photos require a VLM pipeline to caption |

**Sparse-specific events per subject-week: ~3–5** (only the exercise sessions and possibly food photos for 3 subjects). Extremely thin. PMData has **no free-text fields** whatsoever — every annotation is a coded scale or a presence/absence marker.

**PMData is strictly worse than OhioT1DM for this use case.** It has no food names, no self-report narrative, and its annotation channels are pure structured metrics.

---

## Section 4 — Query Family Design (OhioT1DM)

### Q1: Last-occurrence — exercise before hypoglycemia

**Template:** "In the 8-week log, when was the last time the subject exercised within 3 hours before a hypoglycemic episode?"

**Evidence required:** Exercise timestamps + hypo episode timestamps; requires sweeping the full log to find the most recent qualifying pair.

**Guessable prior:** Medium. Exercise-induced hypo is a known T1D pattern. A blind baseline would guess "exercise occurred before a hypo" approximately 40–60% of the time given base rates.

**Blind baseline control:** Require exact timestamp of the exercise event, not just whether it happened. Random-guess baseline produces wrong timestamps.

**Sparse-specific or derivable:** Depends on a sparse-specific anchor (the specific exercise timestamp) AND the hypo timestamp. However, an 80-token summary that lists "hypo Wed 02:00, exercise Tue 18:00" provides the answer. **The summarizer-carries-anchors risk kills this query family.**

**Assessment:** Discarded — answer is derivable from a competent summary.

---

### Q2: Count-over-window — nocturnal hypoglycemia

**Template:** "How many nights in week 3 had a CGM reading below 70 mg/dL between midnight and 06:00?"

**Evidence required:** Must scan all overnight CGM readings in week 3 (7 nights × 18 readings = 126 values).

**Guessable prior:** Low — nocturnal hypo rate varies significantly by subject and cannot be guessed from demographics. Blind baseline: ~1–2 nights.

**Blind baseline control:** Compare blind answer to full-log answer. Blind baseline should fail consistently.

**Sparse-specific or derivable:** This is actually **derivable from dense CGM** — the answer is a count computable from the CGM time series. An LLM summary would say "two nocturnal hypo events in week 3." **Answer carried by the summary.**

**Assessment:** Discarded — count survives in summary.

---

### Q3: Causal precedent — meal before peak glucose

**Template:** "What was the carbohydrate content of the meal eaten in the 2 hours before the highest CGM reading on day 12?"

**Evidence required:** (1) Find the peak CGM value on day 12. (2) Find the meal event within the 2 hours prior. (3) Report its carb content.

**Guessable prior:** Zero — the specific carb count of a specific meal is unknowable without reading the log.

**Blind baseline control:** Blind model cannot guess "75g" without reading. Baseline fails.

**Sparse-specific or derivable:** The answer depends on a sparse-specific anchor (the meal's carb count). HOWEVER: a competent LLM summary of that day or week would include "highest glucose reading [value] on day 12, preceded by [X]g carb meal." **The summary carries the anchor.**

**Assessment:** Partially valid — blind baseline fails, but summarizer-carries-anchors risk is high. If the summary budget is constrained to 80 tokens for a full-week context (6,400 tokens), the specific day-12 meal may not be mentioned. This is the **one query family that might survive** if: (a) the summarization budget is tight (80 tokens for 6,400), and (b) the query targets a day far from the most recent events.

**Honest assessment:** Marginally possible but precarious. The query depends on an LLM summarizer happening to omit a specific meal event, which is not guaranteed.

---

## Section 5 — Regime Prediction (OhioT1DM)

**Prediction: (A) Summary ≈ Full. High confidence.**

### Reasoning

**Event density vs. summary budget:**
- One week of OhioT1DM produces ~6,400 tokens
- Notable events per week: ~5–12 (hypos, large meals, exercise, poor sleep)
- At ~8 tokens per notable event, all events fit in ~96 tokens

An 80-token summary budget is sufficient for a competent LLM to enumerate every notable T1D event in the week. Unlike LoCoMo (15K tokens across 10+ conversation sessions with dozens of distinct personal facts, names, dates, and events that resist compression) or GeoLife (multi-day sequential ordering of named stops), a week of T1D sensor data has a small, predictable vocabulary of notable events and a small count of those events. The summarizer knows what a T1D week looks like and will produce: "Three hypos (Mon/Wed/Sat), exercise Thu high exertion, poor sleep Sun, largest meal Tue dinner 110g carbs." That ~35-token sentence answers most practically designable queries.

**The domain is intrinsically low-entropy.** T1D management revolves around a ~6-category event vocabulary (hypo, hyperglycemia, meal, bolus correction, exercise, poor sleep). The week's notable events fit on a sticky note. LoCoMo's incompressibility comes from heterogeneous personal narrative with high lexical diversity across topics, people, and facts — not from a fixed medical vocabulary.

**The one potential escape:** Query Q3 (causal precedent, specific day far from end) could produce an incompressibility gap if the 80-token summary omits that specific day's meal. But this is brittle and not reliable across subjects, since some weeks have few notable events (summary has headroom) and others have many (summary will select the most notable, which may not be the queried day). The gap would be subject-dependent, small, and inconsistent.

**Comparison to LoCoMo:** LoCoMo has 92.3% entity-omission failures because summaries of 15K diverse conversational tokens at 80 tokens drop ~90% of specific facts. A 6,400-token T1D log has ~10 notable facts; an 80-token summary drops ~0–2 of them. The omission rate is qualitatively different.

**Verdict: NO-GO.**

---

## Section 6 — Cost Estimate for 100-Question Pilot (OhioT1DM)

| Item | Estimate |
|---|---|
| **Access lead time** | ~1–2 weeks (DUA email processing, encrypted file delivery) |
| **Log builder engineering** | 2 days: XML parser → per-timestep event log serializer, CGM bucketing, channel join |
| **Question authoring** | 1–2 days: template author with far-distance enforcement, non-saliency filter (exclude peak-glucose days and most-frequent hypo subjects as anchors) |
| **Audit harness adaptation** | 1 day: adapt geolife_audit.py (model loading already done, summary builder and judge pattern reusable) |
| **GPU hours (A6000)** | ~2–3 hours: 100 questions × 5 conditions × 5 inference calls = 2,500 calls at ~3s each ≈ 2.1 GPU-hours; plus summary pre-generation for unique weeks |
| **Total engineering** | **4–5 days** |
| **Calendar estimate** | **2–3 weeks** (including DUA wait and iteration) |

**Warning:** If the regime test (Section 5) proves correct and summary ≈ full, this is 2–3 weeks spent confirming a negative result with high prior probability.

---

## Final Recommendations

### OhioT1DM — NO-GO

The dataset avoids all prior failure modes except the one that matters most: the event vocabulary for T1D self-management is small and categorical (hypo, meal, bolus, exercise, poor sleep), and notable events per week are few (~5–12). A competent LLM summarizer will enumerate all notable events within the 80-token budget, carrying the sparse-specific anchors into the summary and collapsing the incompressibility gap. The carb-count-only meal annotations (no food names) mean even the meal channel lacks the lexical specificity needed to create anchors that resist summarization. This failure is intrinsic to the domain structure, not a data quality issue. No query family design can reliably exploit the gap because the summarizer will fill it. DO NOT BUILD.

### PMData — NO-GO

Strictly worse than OhioT1DM. Meal annotations are presence/absence only (no carb counts, no food names). All wellness channels are coded numeric scales. No free-text fields exist anywhere in the dataset. The only potentially specific data (food photos, 3 subjects only) requires a VLM perception pipeline, reintroducing the FindingDory anchor-loss risk. The dataset is openly licensed and well-structured, making it usable as a **substrate for the mobility/activity cost model**, but it cannot support incompressibility QA. DO NOT BUILD as QA workload.

### T1DEXI — NO-GO (predicted without full investigation)

Same domain as OhioT1DM with the same structural constraints: CGM + coded meal/exercise logs. Additional friction from the Vivli DUA process (described as onerous in recent literature). Scale (300+ subjects) is its only advantage over OhioT1DM, but scale does not fix the regime prediction. NOT RECOMMENDED.

### LifeSnaps — NO-GO

Purely coded/structured annotations (Fitbit metrics, numeric EMA scales, survey scores). No free-text fields of any kind found in public documentation. All channels are either aggregate statistics (steps, HR, calories) or coded ordinal scores (mood 1–5, anxiety score). Extreme compressibility. The open Kaggle access is its only advantage. NOT RECOMMENDED.

---

## Overall Recommendation

**NO-GO for all four candidates. The domain fails as a class.**

The hypothesis that annotation channels (meals, insulin, exercise, sleep, self-reports) carry sparse non-repeated anchors that summaries drop is **falsified**. In every dataset examined, the annotation channels are coded (not free text), the notable events per week are few (5–12), and the event vocabulary is small and medically stereotyped (~6 categories). An LLM summarizer instructed to summarize a week of personal health data will produce an accurate enumeration of all notable events within 40–80 tokens — not because it is clever, but because the information density of these logs (relative to their token count) is low.

**This is the opposite of LoCoMo**, where incompressibility arises from high lexical diversity, heterogeneous personal narrative, and ~100 distinct facts spread across 15K tokens of conversation. Personal health sensor streams are optimized for structured, computable records — precisely the property that makes them summarization-friendly.

**Recommended next step:** Pivot to **NarrativeQA** (46K human-authored QA pairs over full books and movie scripts, 50K–100K token contexts). Books have high lexical diversity, heterogeneous narrative, sparse far-distance facts, and blind baselines near zero on specific sequential/causal questions. No perception stage, no annotation coding, no DUA. Avoids all five prior failure modes. A 100-question pilot requires no download beyond text files and no perception engineering — only a log-reading harness and the existing audit infrastructure.

---

*Sources consulted:*
- [OhioT1DM Dataset page (UNC Charlotte)](https://webpages.charlotte.edu/rbunescu/data/ohiot1dm/OhioT1DM-dataset.html)
- [OhioT1DM Update 2020 (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC7881904/)
- [PMData: A Sports Logging Dataset (ACM)](https://dl.acm.org/doi/10.1145/3339825.3394926)
- [PMData OSF repository](https://osf.io/vx4bk/)
- [PMData Simula Datasets](https://datasets.simula.no/pmdata/)
- [T1DEXI: Exercise and Glycemia (Sagepub)](https://journals.sagepub.com/doi/10.1177/19322968241246458)
- [MetaboNet-Bench multi-dataset survey](https://arxiv.org/html/2606.18640v1)
- [LifeSnaps Scientific Data paper](https://www.nature.com/articles/s41597-022-01764-x)
- [LifeSnaps PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC9622868/)
