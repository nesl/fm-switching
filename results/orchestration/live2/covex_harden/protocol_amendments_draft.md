# DRAFT protocol amendments for CLAUDE.md

**NOT APPLIED. `CLAUDE.md` is untouched.** Each amendment below is written as text that slots into
the named section, in the protocol's existing voice, with a motivating failure cited in the style
the file already uses for E30, E31, E32 and E36. Most of these failures have no E-id yet, so they
are cited by what they were.

Six amendments, in the order the sections appear in `CLAUDE.md`.

---

## 1. Mechanism verification, Step 2 — require the READ, not the write

**Insert after the existing Step 2 table instruction:**

> For every link, name the **read** that consumes the implementing quantity, not merely the place
> it is set. Give the file and line of the code that *uses* the value to change a decision. A
> quantity that is written and never read is **ABSENT**, and is a stopping condition exactly as a
> zero or a constant is.
>
> *Motivating failure:* `desired_tier` was set by two actions that were dispatched by name,
> counted in `self.counts`, and handled by a named branch in the coordinator, so every surface
> sign said the mechanism was live. Across all of live2 it had **three references: one declaration
> and two writes, and no read**. `RecallAction.representation` had the same shape until `e924005`.
> A write-only field is non-zero, varies by arm and by condition, and is instrumentable, so **it
> satisfies Step 2 as written while implementing no causal link at all**; the Step 4 negative
> control also passes, because disabling the writes correctly collapses to the null.

---

## 2. Mechanism verification, new Step 2b — prove the switch moves a decision BEFORE scoring it

**Insert as a new step after Step 2:**

> **Step 2b — Confirm the switch reaches a decision.** Before scoring any A-versus-B comparison,
> run both conditions on one cell and diff the decision logs. Report the number of differing
> decisions and the first one. If the logs are identical, the comparison has not been run: the
> result is an **ABSENT LINK**, never a negative. Confirm also that each switch arrived at the
> object under test with its declared type and value, not merely that it was passed.
>
> This costs one cell and is run **before** the sweep, not after a suspicious null.
>
> *Motivating failure:* five switch-plumbing faults in three nights, every one found only after a
> null had been produced and nearly written up. A `--candidate` parser turned `mu_mode=scarcity`
> into a literal key; `make_arm` silently discarded kwargs so `c_inflight=8` returned the default
> arm; an int field declared `int` was coerced to `bool`, turning 2 into 1; B2's `z[RC]` reached
> 543.58 and no decision; RCprio never fired even at a slack threshold equal to the entire
> deadline.

---

## 3. Rule 2 — "inconclusive" resolves into five distinguishable causes

**Replace the second bullet of Rule 2 with:**

> - **Inconclusive:** the mechanism did not operate as specified. State **which** of the following
>   applies, because the diagnostic and the remedy differ and only the last is a finding about the
>   policy:
>   - **cancelled by geometry** — the quantity is alive and cancels between the compared branches,
>     so it cannot affect the difference. *(B2's deficit; spec 5.3 state value, non-zero in 96.6
>     percent of branches and exactly equal across them in 12,898 of 12,898 candidates.)*
>   - **unexpressible** — the mechanism fires but the harness discards the channel it acts
>     through. *(the action `order` field; `desired_tier`.)*
>   - **unscorable** — the objective cannot see the quantity the mechanism changes. *(a 12 to 25
>     percent GPU-second spread moving ΔJ by zero to nine decimal places.)*
>   - **unexercised** — the mechanism is reachable but no condition in the run reaches it.
>     *(RELOAD is offered only at HOST-WARM and no recall reached HOST-WARM; **E36, E36b and E36c
>     were this case**.)*
>   - **fired and did not help** — the mechanism operated and produced no effect. **This is the
>     only one that is evidence about the policy**, and it is still not a settled negative unless
>     Step 4 showed the control changed the result.

---

## 4. Results consistency check 3 — two counterparts to the constant

**Insert after the existing check 3 text:**

> A constant where a distribution is expected is only the most visible of three shapes. Also flag:
>
> - **an artefact spread** — values that differ across arms by a credible margin while deriving
>   from a quantity that cannot carry the meaning claimed. Before trusting a spread, state what the
>   values *are* and confirm they can mean what the column says.
> - **a real effect averaged into undetectability** — a population mean below its own noise floor
>   that conceals a large effect on a stratum. Where an effect is expected to be concentrated,
>   report the stratum and the mixing weight beside the mean.
>
> **A constant advertises breakage; a plausible spread does not**, and an averaged-out effect reads
> as an equivalence, which is wrong in both directions at once.
>
> *Motivating failures:* an accuracy column spread 0.0289 to 0.2143 across arms while every cloud
> answer was a placeholder `"X"` that never matched a gold letter, so the spread tracked only how
> many questions each arm delivered on time and **ranked the arms backwards**. Separately, a +1.18
> pp population gap with a CI including zero concealed **+17.5 pp on the 11.5 percent stratum**
> where the recent window misses the evidence.

---

## 5. Citing results — mark the register at the point of use

**Insert under "Citing results":**

> State the **register** of every number where it is used, not only where it is derived:
> **observed count** against **constructed bound**; **applied locally** against **pushed and
> verified on origin**; **one traced unit** against **a full table**. A number in the wrong
> register is not a wrong computation and will survive every arithmetic check.
>
> *Motivating failures:* a worst-case construction reported as a census; "committed to
> `coordinator.py`" meaning written into the file and read as git-committed and pushed, which
> unblocked a session against a change that was not on origin; and a single category's delta
> (`counting_objects_events`, D2 2.8 pp below RICH) generalised to a direction, when across all
> eight categories D2 was **better on four**, led by `location_trace` at **+17.2 pp**.

---

## 6. New results consistency check 7 — validate the BEFORE condition

**Insert as check 7:**

> **7. Validate the control, not only the result.** In any before/after or arm-versus-baseline
> comparison, cross-check the **control** arm's own numbers against its committed values before
> reading the comparison. A broken control passes every check applied to the treatment, because
> the treatment is fine.
>
> Include a **positive control**: a known-good committed arm must pass the check being applied. If
> it fails, **the check is broken, not the arm**. An impossible failure and an impossible success
> are equally diagnostic, and a reviewer watching only for implausible *results* will catch
> neither.
>
> *Motivating failures:* a before-condition gave dashcam 0.0821 and **0 recalls** against that
> arm's committed 0.8164 and 14 of 35 — *a "before" condition that destroys the arm is not a
> before condition* — and it was caught by the **magnitude, not the method**, so a subtler break
> would have passed. A legality pass reported 2,834 to 3,000 illegal actions for **every** arm
> including the committed `b7` control, which cannot be illegal.
>
> **The general shape:** a comparator planning at one price while charged another, and a broken
> control arm, are the same blindness — **a side of the comparison that is never audited.**
> Arm-versus-arm checking cannot see either, because every arm is compared against the same
> unexamined bar.

---

## Note on scope

Amendments 1, 2 and 3 strengthen the mechanism protocol; 4, 5 and 6 strengthen the consistency
protocol. **Each was earned by a failure that the protocol as written did not catch**, and in
every case the failure produced a plausible number rather than an obvious error. None of them
would have been caught by running the existing checks more carefully.
