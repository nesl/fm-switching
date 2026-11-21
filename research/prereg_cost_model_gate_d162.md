# PRE-REGISTERED before any refit: the D162 cost-model gate

Session D (flash / A6000), 2026-11-21 08:50. Committed **before** the load sweep exists and before
any refit is run, so nothing here can be tuned to a result. D162, with D159 (B) and D160 (2).

## 1. Regime classification, from committed cells, never from offered load

A request is classified by the **observed first-token lag of its own 100 s window of submit time**,
pooled over all requests in that window (the window p50). **Offered load is not used**, because the
bracketed-knee result that would have licensed a load threshold is **withdrawn**: crossing and
non-crossing cells interleave across 4,670 to 4,707 uncached tok/s
(`reports/study_saturation_knee.md`, retraction).

| zone | window first-token p50 | use |
|---|---|---|
| **HEALTHY** | **<= 2.781 s** | **the only data fitted or tested** |
| UNCLASSIFIED | 2.781 s to 31.0 s | excluded from fit and test, reported as a count |
| **COLLAPSED** | **> 31.0 s** | **diagnostic only, never pass or fail** |

**Where the two bounds come from, measured over 680 windows in 58 committed cells:**

- **2.781 s** is the largest window p50 observed in **any** cell of the committed 26-cell gate set,
  attained by `always-cloud-fcfs_n16_s4_1200s_h27_3t` at t = 400 s. It is a committed-data maximum,
  not a round number.
- **31.0 s** is below the smallest window p50 of every severe cell (the observed minimum on that
  side is 31.89 s).

| zone | windows | share | requests | warm requests | warm share |
|---|---|---|---|---|---|
| HEALTHY | 596 | **87.6 percent** | 626,504 | **220,256** | 35.2 percent |
| UNCLASSIFIED | 22 | **3.2 percent** | 24,371 | 10,242 | 42.0 percent |
| COLLAPSED | 62 | 9.1 percent | 66,027 | 36,899 | 55.9 percent |

The window distribution is sharply bimodal: p50 0.381 s, p75 0.515 s, then p90 **19.240 s**. The
middle holds **3.2 percent** of windows, which is why a three-zone rule is honest here and a binary
one would not be: the exact bound barely matters, and the classification is not doing hidden work.
All 22 unclassified windows are listed in the measurement output so the exclusion can be audited.

**Pre-registered sensitivity:** moving the healthy bound anywhere in 2.0 to 5.0 s, or the collapsed
bound anywhere in 20 to 31 s, must not change the verdict. If it does, the verdict is an artefact of
the bound and will be reported as such rather than as a pass or a fail.

## 2. The form, non-negative by construction

```
first_token  ~  b0  +  b1 * uncached_tokens  +  b2 * queue_uncached_ahead
```

fitted by **non-negative least squares** (Lawson-Hanson active set, pure Python, in the house style
of the committed Gauss-Jordan solver), with **b0, b1, b2 >= 0**. Every feature is non-negative, so
**every prediction is non-negative by construction** and the physical-impossibility failure that
sank the D156 (4) gate cannot recur. That also means "0 percent negative predictions" stops being a
test and becomes a structural property; it is reported, not scored.

`queue_uncached_ahead` is the **explicit queueing / capacity term** D159 (B) requires: the sum of
**uncached tokens** over requests submitted but not yet done at this request's submit instant. It
replaces the committed gate's raw `overlap` **count**, because what a queue makes you wait for is
work, not requests, and the 160x overlap spread that broke the linear form was a count standing in
for work.

**Decode** keeps the committed form, also under NNLS: `decode ~ c0 + c1 * queue_decode_ahead`.

## 3. The split, with a precondition that is checked before any verdict is read

- **Fit:** healthy-zone requests from the sweep at **seed 4**.
- **Held out:** healthy-zone requests from the sweep at **seed 5**.
- **PRECONDITION, checked first:** `warm_rows_held_out > 0`. If it is zero the split is **rejected**
  and no verdict is reported. This is the exact failure of the committed `by_arm` split, which held
  out the hybrids and so held out the only arms with no warm rows at all, declaring
  `warm_rows_held_out: 0` in `cf_ontime_model_frozen.json`. The healthy zone holds 220,256 warm
  requests, so the precondition is satisfiable, and the sweep arm below is chosen to guarantee it.

## 4. Pass criteria, declared now

| | criterion |
|---|---|
| precondition | `warm_rows_held_out > 0` |
| negative predictions | 0 by construction, reported not scored |
| **held-out first-token `ratio_p50`** | **within 0.80 to 1.25** |
| **held-out WARM-stratum `ratio_p50`** | **within 0.70 to 1.43** |
| sensitivity | verdict unchanged across the bound ranges in section 1 |

The committed positive control (`cost_model_gate.json`, `by_seed`) achieved 0.91 to 1.13 overall and
0.9108 on warm, using the same code path on cells that never straddle the transition. So these
criteria are **achievable but not trivial**, and they are set from that control rather than from any
sweep result, which does not exist yet.

**Collapsed-zone error is computed and reported as a diagnostic and can neither pass nor fail the
gate**, per D162.

## 5. The load sweep: light to the healthy edge

**Arm: `warm-all-lru-reactive`**, held fixed. Why this one, and the reason is measured rather than
aesthetic: it is the only warming arm that **never crossed in any committed cell** (its CAL1F cell
at 4,511.7 uncached tok/s is the **highest non-crossing cell in the entire 56-cell set**, and its
EP-G cell sits at 0.446 s), while still producing **91.3 percent warm requests** on EP-G. So it
generates the warm rows the split needs without itself leaving the healthy regime, which is exactly
what a healthy-regime warm fit requires.

**Load lever: device count `n`**, which is exogenous to the policy. A policy-driven lever would
confound load with the thing being priced.

**Cells: `n` in {4, 8, 12, 16, 20}, seeds 4 and 5**, EP-G + per-frame at the 3 s deadline, so the
fit regime matches the regime MARGIN_CF is scored in. Ten cells.

**"Up to the healthy edge" is enforced after the fact, not guessed:** any cell with a window above
2.781 s contributes **only** its healthy windows to the fit, and a cell whose windows are mostly
above it is reported as a diagnostic. `n = 20` is the one that may cross (a committed `n20` cell of
another arm reached 5,444 tok/s and 77 s), so the sweep **brackets** the edge rather than being
designed to reach collapse.

## 6. MARGIN_CF

Set **once**, from the **held-out p90** under **D157 (2) units**: population = every robot question
released in the held-out cells, error = `0.250 * |P_hat - 1[on time]|`, p90, with `P_hat` frozen and
hashed before scoring. **Not** the held-out p90 absolute first-token error in seconds, which D154 (2)
read literally would give, and which the D156 (4) run showed to be 41.17 s, larger than every
deadline in the system.

MARGIN_CF is set only if the gate **passes** all of section 4. Session B rebuilds `P_hat` on this
split, per D159 (B) and D161.

## 7. Step 0: what would invalidate this run

- **The sweep arm leaves the healthy regime at low `n`.** Then there is no healthy warm data at
  several loads and the fit spans too little range. Detect by the per-cell window classification
  before fitting.
- **`warm_rows_held_out` comes out 0.** Precondition, checked first, verdict withheld.
- **The healthy zone turns out to carry no load variation**, i.e. `queue_uncached_ahead` is near
  constant across the sweep. Then the queueing term is **CONSTANT** in the CLAUDE.md Step 2 sense
  and the sweep cannot identify it; that is a stopping condition, not a fit to report.
- **Any pre-race-fix cell enters the sweep.** It cannot: these are new cells. But the D159 (E)
  finding that pre-fix 400s **mask saturation** by failing fast means a contaminated cell would look
  healthier than it is, and would therefore be misclassified into the healthy zone. All sweep cells
  are post-fix by construction.
- **The verdict moves when the bounds move** inside the section 1 sensitivity ranges.

## 8. Register

- The two bounds, the three-zone shares, and the 220,256 healthy warm requests are **MEASURED** over
  680 windows in 58 committed cells.
- The pass criteria are **DECLARED**, calibrated against the committed positive control.
- The sweep design is **DECLARED**; its healthy edge is **not yet measured** and the sweep exists to
  find it.
- Nothing in this document is fitted. No sweep cell exists yet.
