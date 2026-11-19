# D138 P1: dry screen of the H100's hybrid components

Session 2. CPU-only dry screening on flash, taking it off the H100. **Regime 3 throughout**:
`DEFAULTS["representation"]` was restored to `D2` at `a0bcb51`, so the b7 base takes the **full
history** (1,381 to 18,931 tokens, median 9,481) and **any RECENT share measured here is a
component CHOOSING it, never a default supplying it.**

`live2/hybrid/` is the H100's module and is read, never edited. The arms register only on package
import, which no flash-owned file performs, so my driver imports it and **refuses if any
configuration in the pair list is unregistered** rather than discovering it mid-sweep.

---

## 1. THE GATE: which components move a decision. Run BEFORE any cell is scored

Isolating each component against **its own prerequisite**, seed 0, decision-log diff **plus**
emitted-action observables, since `decision.jsonl` sees neither representation nor session actions.

| n | component | pair | MOVED | decision rows | representation | credit axis |
|---|---|---|---|---|---|---|
| 12 | **C1 alone** | base to c1 | **NO** | **0** | 0 | unchanged |
| 12 | C5 alone | base to c5 | yes | 6,339 | 14 | unchanged |
| 12 | C1 under the C5 cap | c5 to c1c5 | yes | 6,262 | 12 | unchanged |
| 12 | C2 (k_r 1.0 / 2.0) | c1 to c1c2k | yes | 66 | 0 | unchanged |
| 12 | **C3 (k_r 1.0 / 2.0)** | c1c2k to c1c2kc3 | yes | 3 | **2** | **INJECTED 27 to INJECTED 25 + CHOSEN 2** |
| 16 | **C1 alone** | base to c1 | **NO** | **0** | 0 | unchanged |
| 16 | C5 alone | base to c5 | yes | 7,931 | 28 | unchanged |
| 16 | C1 under the C5 cap | c5 to c1c5 | yes | 7,434 | 22 | unchanged |
| 16 | C2 (k_r 1.0 / 2.0) | c1 to c1c2k | yes | 121 | 0 | unchanged |
| 16 | **C3 (k_r 1.0 / 2.0)** | c1c2k to c1c2kc3 | yes | 6 | **2** | **INJECTED 35 to INJECTED 33 + CHOSEN 2** |

## 2. THE PREREQUISITE STRUCTURE, settled against the code and confirmed by measurement

Two descriptions reached me and **neither is right**. One said C2 needs C1 and C3 needs C1+C2, so
only C1 and C5 are testable alone. The other said C1, C2 **and** C3 only act with C5's cap on.

**Measured:**

| component | gated on | evidence |
|---|---|---|
| **C1** | **C5** | 0 rows differ at **both** sizes without it; 6,262 and 7,434 with it |
| C2 | C1 (not C5) | 66 and 121 rows differ **without C5** |
| C3 | C1 + C2 (not C5) | 3 and 6 rows differ **without C5** |
| C5 | nothing | testable alone |

**The mechanism for C1 is visible in the module:** without C5 there is no cap, so
`keep = {all items}` and C1's index sort merely reorders a set that is released **in full**. It
needs the cap to have anything to select between. **So the user's note is right for C1 and wrong
for C2 and C3**, and my own earlier reading was half right: C2's reserved slot **is** inside the
`if self.sw["c5"]` branch, but C2 has a second effect outside it through the at-risk flag the sort
consults whether or not a cap applies.

**A C1-alone cell would have produced a null that is a PREREQUISITE FAILURE, not a component
result**, and nothing in the configuration name says so. This is the second Step 0 case today,
after the unimported `__init__.py`.

**C1's gating is NOT size-dependent**: 0 rows at 12 and at 16. That is worth stating because three
verdicts this week needed a size scope, and this one does not.

## 3. THE EXERCISABLE SET is smaller than twelve configurations suggests

| component | status |
|---|---|
| **C6** chooser | **OFF** until the chooser lands. Category 4, unexercised. |
| **C4** retention | **placeholder emitting no session action until memory pressure exists.** Category 4; becomes testable when pressure lands. Confirmed: **session actions never differ in any pair**. |
| C1 | requires C5 |
| C2, C3 | require C1; **not** C5 |
| C5, base | testable alone |

**C4's inertness is confirmed rather than assumed:** the `session_actions_differ` column is
**False in all 14 pairs**, so no hybrid configuration emits a session action at all.

## 4. C3's characteristic decision, and why the credit axis was needed

Amendment B requires a port's characteristic decision to occur at least once. **C3's is "send an
at-risk, full-history-infeasible recall as RECENT", and it fires exactly twice at 12 devices and
twice at 16.**

**The credit axis is the only thing that shows this.** Every other configuration is
`INJECTED` on every recall, because the b7 base names no representation and takes the restored D2
default. C3 flips exactly two of them to `CHOSEN`. **A RECENT share read from the effective axis
alone would not distinguish a component choosing RECENT from the default supplying it** - and in
Regime 3 the default supplies D2, so a naive reading would have shown C3's RECENT share as
indistinguishable from noise rather than as two deliberate choices.

**Two decisions is small, and that is itself the finding to carry into scoring:** C3 is a
narrow-mechanism component, so a cell-level outcome difference attributable to it will be at most
a couple of questions, and should not be expected to move a capacity cell on its own.
