# Study O — Q4 re-run on the 845-question pool (flash-attn)

**Date:** 2026-10-17
**Trials:** `results/sember/study_o/study_o_q4_trials_fa2.jsonl` — **2,535** (3 cells × 845)
**Scripts:** `experiments/sember/study_o_q4.py --fa2`, `study_o_q4_analyze.py --fa2`
**Backend:** `flash_attention_2`, asserted on all three towers at every model load and recorded
per trial (`attn_implementation` is `flash_attention_2` on 2,535/2,535 rows).
**Compute:** 6.05 h wall (23:06 → 05:09), 4.92 h summed in-trial latency, A6000 (flash, cuda:1).

---

## THIS RUN DOES NOT REPRODUCE THE COMMITTED Q4 RESULT

The committed Q4 (`reports/study_o_q4_results.md`, 2026-10-15) ran on a **520-question pool**.
This run uses an **845-question pool**. **The pool changed; this is not a replication of the
committed numbers, and nothing here supersedes them.**

**Why it changed.** The committed Study O was halted at the §8.2 cell-balance gate: 12 of 24
cells were below the n≥30 threshold because the required S-EMBER videos were absent from disk.
A greedy set cover identified the minimum repair — **84 videos, 9.97 GB** — which was fetched on
2026-10-16. With those videos present the question pool built by the same deterministic
constructor grows from 520 to 845, and every cell reaches ≥30. Q1–Q3 are no longer blocked.
Q4 was re-run on the same enlarged pool so the Study O cells stay internally consistent with
each other rather than split across two pools.

**The 520 result stays in the record.** `reports/study_o_q4_results.md` and
`results/sember/study_o/study_o_q4_trials.jsonl` are unmodified and remain the committed Q4.

**Comparison rule applied throughout this report:** no figure from the 845 pool is placed next
to a figure from the 520 pool without this sentence attached — *these come from different
question pools (845 vs 520) and are not a before/after measurement of anything.* The two runs
also differ in attention backend (flash-attn here, SDPA there), so any pairwise difference below
has **two** uncontrolled factors, not one.

---

## VERDICT — unchanged in substance, changed in reason

> **Coverage-based escalation does NOT convert into end-to-end accuracy gain.**
>
> Primary test, remote = 8B-I × RICH, e = 0.2:
> **acc(d) − acc(c) = +0.38 pp, 95% CI [−1.20, +1.69]** (clustered bootstrap, 2,000 resamples,
> 234 video clusters). **CI includes 0.** gap_closed_accuracy = **2.9%**.
>
> ## **K4 FIRES** — reason **(ii)**: the predictor's coverage ranking does not correlate with
> local-vs-remote accuracy differences.
>
> The Study N2 runtime-signal claim **stays at the coverage level only**.

**What changed from the committed run, and it is not the verdict.** On the 520 pool K4 fired for
reason **(i)** — local and remote accuracy were too close (33.85% vs 33.27%) for routing to
matter at all. On the 845 pool that premise no longer holds: the remote model is genuinely
better (32.78% vs 36.21%, net +3.43 pp, b=118 rescues / c=89 breaks). **There is now a real
local-vs-remote gap for a router to exploit, and the coverage predictor still fails to exploit
it.** That is a stronger negative than reason (i): reason (i) says the test was degenerate;
reason (ii) says the test was live and the signal lost it. *(Both statements are about different
pools and are not a measured change — see the comparison rule above.)*

Under **CLAUDE.md Rule 2** this null is classified **Real negative** on the 845 pool: the
mechanism was present and exercised (the local/remote accuracy gap is non-zero at +3.43 pp, the
predictor's base rate is 0.296 and varies across questions, and the accuracy oracle recovers
+13.28 pp of headroom, so the quantity the policy could in principle capture is large and
non-degenerate), and the predictor-driven policy still did not beat random escalation at the
same rate.

---

## 1. Cells

| cell | role | n | accuracy | D4 coverage | frames (med) | input tok (med) | latency (med) | budget_hit | think_closed |
|---|---|---|---|---|---|---|---|---|---|
| 4B-I × RECENT | local | 845 | **32.78%** | 88.5% | 121 | 12,437 | 2.31 s | 0 | n/a (instruct) |
| 8B-I × RICH | remote (Instruct) | 845 | **36.21%** | 100.0% | 231 | 12,597 | 3.31 s | 0 | n/a (instruct) |
| 4B-T × RICH | remote (Thinking) | 845 | **30.89%** | 100.0% | 231 | 12,599 | 8.47 s | 5 | 840/845 |

D1–D4 fixes are as applied in the committed run and were verified present in this script before
launch, not re-implemented.

Coverage split on the local cell: `evidence_covered` trials score **34.4%** (n=748), uncovered
trials **20.6%** (n=97). Coverage does predict accuracy at the item level; what it fails to do
is predict *where the remote model wins*, which is what the router needs.

## 2. Policy grid

**Remote = 8B-I × RICH** (paired n = 845, 234 video clusters)

| e | (a) never | (b) always | (c) random | (d) predictor | (e) evidence oracle | (f) accuracy oracle | **d − c** | gap_closed |
|---|---|---|---|---|---|---|---|---|
| 0.1 | 32.78% | 36.21% | 33.12% | 33.96% | 33.73% | 42.72% | +0.84 pp | 8.8% |
| **0.2** | 32.78% | 36.21% | 33.47% | **33.85%** | 35.86% | 46.75% | **+0.38 pp** | **2.9%** |
| 0.3 | 32.78% | 36.21% | 33.81% | 33.85% | 37.16% | 46.75% | +0.04 pp | 0.3% |

**Remote = 4B-T × RICH** (paired n = 845)

| e | (a) never | (b) always | (c) random | (d) predictor | (e) evidence oracle | (f) accuracy oracle | **d − c** | gap_closed |
|---|---|---|---|---|---|---|---|---|
| 0.1 | 32.78% | 30.89% | 32.59% | 33.61% | 33.49% | 42.72% | +1.02 pp | 10.0% |
| **0.2** | 32.78% | 30.89% | 32.40% | **33.73%** | 34.44% | 45.21% | **+1.33 pp** | 10.4% |
| 0.3 | 32.78% | 30.89% | 32.21% | 34.08% | 34.67% | 45.21% | +1.87 pp | 14.4% |

Primary (e=0.2): +1.33 pp, 95% CI **[−0.17, +2.59]**, CI includes 0.

**K4 does not fire on this configuration, and that must not be read as a positive result.** K4
is a conjunction — (d)−(c) < 1 pp **and** CI includes 0 — and only the first conjunct fails.
The CI still includes zero, so there is no evidence the predictor beats random here either. The
same non-firing-but-not-positive pattern appeared on the 520 pool. *(Different pools; not a
measured change.)* Escalating to 4B-T is also escalating to a **worse** model overall (30.89% vs
the local 32.78%), so the policy's apparent lift is being produced on top of a remote arm that
loses on average, which is the opposite of the setting the escalation claim describes.

## 3. Results consistency check (CLAUDE.md, six checks)

**1. Cross-check against committed measurements.**

| quantity | this run (845, FA2) | prior (520, SDPA) | source | ratio | agree? |
|---|---|---|---|---|---|
| 4B-I × RECENT accuracy | 32.78% | 33.85% | `study_o_q4_results.md` §1 | 0.97× | agree (different pool) |
| 8B-I × RICH accuracy | 36.21% | 33.27% | ditto | 1.09× | agree (different pool) |
| 4B-T × RICH accuracy | 30.89% | 30.00% | ditto | 1.03× | agree (different pool) |
| median input tokens | 12,437 / 12,597 / 12,599 | 12,439 / 12,599 / 12,601 | ditto | 1.00× | agree |
| K4 on primary config | FIRES | FIRES | ditto | — | agree |

All within 2×. The accuracy rows are **not** a backend or pool comparison — the pool and the
backend both changed — and are tabulated only to confirm nothing moved by an implausible margin.
The median-input-token row is the informative one: it is the quantity that should be invariant
to both changes, and it is, to within 2 tokens.

**2. Physical plausibility.** 4B-T generates at a median 206 tokens in a median 8.47 s including
prefill of ~12.6 k input tokens. Backing out prefill at the committed A6000 curve (~7,100 tok/s
→ ~1.8 s) leaves ~6.7 s for 206 tokens ≈ 31 tok/s decode, against the committed 26.9 tok/s
measured on the n=10 sizing trials of this same cell — 1.15×, under the 2× flag. No result here
is faster than the committed curves.

**3. Distribution sanity.** Latency is reported as median with mean alongside: 4B-T median 8.47 s
vs mean 15.43 s, a 1.8× mean/median ratio reflecting a long right tail (5 trials hit the 8,192
budget). No constant-where-a-distribution-is-expected: all three cells show per-trial spread, and
accuracy varies across the e-grid.

**4. Definition audit.** `evidence_covered` is D4's definition — computed per trial from the
timestamps actually sampled, not from the nominal window — identical to the committed run.
A "trial" is one (question, cell) pair; the pool is the deterministic `(video_id, question_id)`
sort over questions whose video is present on disk. **The pool definition is unchanged; only its
membership grew**, because the set of videos present on disk grew. That is the one definitional
quantity that differs between the two runs and it is stated everywhere it bears on a number.

**5. Claim linkage.** Bears on the Study N2 runtime-signal claim (`research/CLAIMS.md`). The
result **weakens** any extension of that claim from coverage prediction to end-to-end accuracy
routing. It does not speak to Q1–Q3.

**6. Proxy validity.** The P4 predictor's `P(needs_escalation)` is a proxy for "this question
needs the remote model". What it actually measures is predicted evidence coverage. The §1
coverage split shows it is a valid proxy for item difficulty (34.4% vs 20.6%) and the policy grid
shows it is **not** a valid proxy for local-vs-remote advantage. That distinction is the finding,
not a limitation of it.

## 4. Runtime estimate vs actual — the estimate missed

Stated per the `research/HOSTS.md` runtime-estimate rule.

| | estimate | actual |
|---|---|---|
| basis | 11.8 s/trial mean, **median 327 generated tokens**, measured on the first **10 trials of the 4B-T × RICH cell of this same run** | — |
| 4B-T cell | 2.74 h | **4.03 h** |
| all three cells | 3.9 h, ±30% → **2.7–5.1 h** | **6.05 h** |

**The actual fell outside the stated band, 1.19× above its upper edge.** Cause: the n=10 sizing
sample had mean 11.8 s against the full cell's mean 15.43 s. The sample's median generated
length (327) was *higher* than the cell's (206), so the miss was not a token-count error — it was
tail undersampling. Ten trials cannot estimate a mean whose distribution has a 1.8× mean/median
ratio; the ±30% band was set from the n=10 range and the true tail is wider than that range
showed. The band was honest about direction and too narrow in width. Recorded here so the next
sizing run uses a tail-aware quantile rather than a range over ten points.

## 5. What is and is not established

- **Established:** on the 845-question pool, with a real +3.43 pp local-vs-remote gap available,
  coverage-based escalation does not convert to end-to-end accuracy. Real negative under Rule 2.
- **Established:** the coverage signal does predict item difficulty (34.4% vs 20.6%).
- **Not established:** anything about the 520 pool from these numbers, or anything about the
  attention backend — both changed together and neither was isolated here.
- **Not addressed:** Q1, Q2, Q3. They are now unblocked at the data level but were not run.
