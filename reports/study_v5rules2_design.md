# D159 (A) + D160: why `deadline_work_at_risk` never fired, and what v5-rules-2 must do instead

Session D (flash / A6000), 2026-11-21. Analysis only, no run. Diagnosis first, because D159 (A)
asks for it and because it decides whether D160 (2)'s replacement is the right shape.

## The diagnosis: it is UNEXERCISED, not broken

`engine_actions.py:141-154`:

```python
def deadline_work_at_risk(obs, targets=None, laxity_fraction=W2_LAXITY_FRACTION) -> bool:
    now = float(obs.now_s)
    for q in obs.recall:
        bound = max(float(q.deadline_s) - float(q.arrival_s), 1e-9)
        if (float(q.deadline_s) - now) < laxity_fraction * bound:
            return True
    return False
```

`W2_LAXITY_FRACTION = 0.3` (`engine_actions.py:95`, D143 ruling B). `obs.recall` is documented at
`cstate.py:13` as "robot recall questions that have arrived, **are not yet answered**, and are not
withheld by a DEFER".

So firing requires a robot question to be **simultaneously unanswered and inside the last 30
percent of its own deadline**. At the committed robot deadline of 3.0 s that means a question still
unanswered **2.1 s or more** after it arrived. Two measured facts make that unreachable:

| | measured |
|---|---|
| robot questions per run, 16 devices | **20** |
| decision epochs per run | **12,001** |
| robot first-token p50 in healthy cells | **0.27 to 0.45 s** |
| wait needed to trip the predicate | **2.1 s** |

Even if every one of the 20 questions occupied a whole epoch while pending, that is **0.17 percent
of epochs**. And in the healthy regime a question is answered roughly **5x inside** the trigger
window, so none of those epochs qualifies either. The predicate is sound code evaluating a
condition the run never produces. Under Rule 2 this is **unexercised**, the same class as E36 and as
RELOAD-at-HOST-WARM: reachable but no condition in the run reaches it. It is **not** the write-only
field failure, because the value is genuinely read at two call sites
(`engine_actions.py:177` and `:220`).

## Why it is also the wrong signal, which is what D160 (2) fixes

The failure the yield was supposed to prevent is the one measured last night: the engine crossing
into a regime where first-token latency runs **31 to 478 s**. That is a property of the **engine
queue**, and `deadline_work_at_risk` cannot see it:

- In the healthy regime nothing is ever at risk by this test, so warming is never shed, which is
  what the 12,001 zero epochs record.
- Once the engine is saturated the deadline is already blown by one to two orders of magnitude. A
  question is then either answered very late or not scored at all, so by the time the predicate
  could fire the collapse has already happened. Shedding warming at that point is too late to
  prevent anything.

So the predicate is **both unexercised in the regime that matters and useless in the regime it was
aimed at**. It cannot be repaired by moving `laxity_fraction`: with 20 questions per run and
sub-second answers in the healthy regime, any threshold either never fires or fires only after
collapse. **This is why D160 (2) replacing it with live engine feedback is the right change and not
a workaround**, and it is also why the guard must key on quantities that move BEFORE the deadline is
missed (deadline work in flight and queued, and the observed first-token lag of deadline requests)
rather than on remaining laxity.

One consequence for the guard's own thresholds, which D160 (2) requires be declared before any live
run and taken from committed cells only: the observable that separates the regimes cleanly in
committed data is **first-token lag of deadline requests**, where the healthy side sits at 0.27 to
0.45 s pooled and never exceeds 2.781 s in any 100 s window across the gate's 26 cells, while every
severe cell exceeds 31 s. The **load** axis must NOT be used, because the bracketed-knee result that
would have licensed a load threshold is withdrawn: crossing and non-crossing cells interleave across
4,670 to 4,707 uncached tok/s, so run-mean load does not determine the regime
(`reports/study_saturation_knee.md`, retraction section). D159 (A)'s instruction to throttle on live
signals and never on a fixed load threshold is therefore not a preference, it is forced by the
measurement.

## What v5-rules-2 is, after D160

v5-rules-2 = base `hybrid-F-lhreq-noc3` + **chunked just-in-time warming** + **the saturation
guard**, with D152 (3)'s per-frame prefilling **withdrawn**.

The withdrawal is worth stating in numbers, because it is the whole point of D160 (1): coupling a
prefill to every uploaded frame made warming cost scale with **request count**, which is what
produced about **84,000 prefills per run** and drove engine overlap from about 10 to about 2,000.
Chunking at 2,048 tokens means a robot session's unwarmed tail is prefilled roughly once per 22
robot frames instead of once per frame, so the prefill count per run becomes a **reported proof**
rather than a side effect. Upload stays per frame, which restores D150 SYNC (1): upload and warming
are decoupled again.

The just-in-time trigger uses the device's **causal** question-rate estimate (D11 / D48) and must
never read the trace's future ask times. That is a Step 2 concern I will prove rather than assert,
because it is exactly the shape of error that would make the arm look good for the wrong reason: if
the horizon test could see when the next question actually arrives, the arm would warm perfectly and
the result would measure the oracle, not the policy.

## Proofs owed before any v5-rules-2 cell runs

From D159 (A) and D160, with how each will be produced:

1. **Guard fires under contention in a dry run and sheds warming.** Count of guard-active epochs
   greater than zero, and warm-ahead actions emitted in those epochs equal to zero.
2. **Prefill request count far below v5-rules.** Per-run count, against v5-rules' approximately
   84,000.
3. **Cached tokens at question time still rise against base.** The arm must still do its job; this
   is the positive side of the ledger and the thing chunking could break.
4. **Step 2b against v5-rules and against base.** Differing decision counts and the first
   difference, on one cell, before the sweep.
5. **0 illegal actions.**
6. **The port rule**, which D159 (A) does not name but CLAUDE.md requires: the count of the arm's
   characteristic decision, chunked warm-ahead, must be non-zero. The bare yield fix would have
   failed exactly this, since its characteristic decision fired 0 times in 12,001 epochs.
7. **No future read** in the horizon test, per the Step 2 concern above.

## Register

- The 20 questions, 12,001 epochs and 0.27 to 0.45 s first-token figures are **MEASURED** from
  committed cells.
- "Unexercised rather than broken" is a **classification** under Rule 2, resting on those
  measurements plus the two read sites.
- The 2.1 s trip threshold is **DERIVED** from `W2_LAXITY_FRACTION = 0.3` and the 3.0 s committed
  robot deadline.
- The approximately 84,000 prefills and the 10 to 2,000 overlap range are the user's figures from
  D160 (1), carried here as given and **not** re-measured by me.
