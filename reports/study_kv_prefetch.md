# StudyKV-PREFETCH: giving the KV-cache baselines the proactive mechanism their own card claims

D155 (5), flash, 2026-11-20. Artefacts: `experiments/orchestration/live2/arms_kvprefetch.py`,
`results/orchestration/live2/kv_prefetch/`.

E-id: **StudyV5-ENGINE** in `research/EXPERIMENTS.md`, which is the committed row for warm-ahead
prefill and whose pre-registered gate is the one applied here verbatim: "the WARM-ALL arm must
carry four proofs before it is scored: well-formedness (zero illegal actions), a fairness digest
against its base, **a NON-ZERO count of its characteristic decision (a warm-ahead prefill)**, and
a Step 2b decision-log diff against its base." This study applies that same gate to the published
KV-cache baselines. **The row update and the `results/INDEX.md` append are not made by this
session**, which does not own those files; the rows they need are drafted in section 9.

Source decisions: D155 (5), and `reports/policy_v5_assessment.md` section I, which is the audit
this work comes from. Interface: `reports/study_engine_actions.md` section 1. Everything here was
read and run from a detached worktree at `origin/main` (`55ec283`); the flash working tree is
hundreds of commits behind and contains none of it.

**REGISTER, FIRST.** Nothing in this report is a measured latency, quality or capacity result.
Every number is an **observed count** from a **DRY decision-path run** with a stub bridge and no
engine: counts of decisions, actions and beliefs, never of seconds. No cell was scored, no
leaderboard row was written, and no committed number moved.

---

## 0. The finding that goes first, because everything else is read against it

**THE PATCH THE BRIEF SAID WAS ON ORIGIN IS NOT ON ORIGIN.** The brief for this work stated that
a patch adding `Observation.live_sessions`, and including it in `known_sessions`, was already on
origin and that proactive warming was therefore expressible for the first time. It is not there.
Checked at `55ec283`, before any arm was written:

| probe | result at `origin/main` `55ec283` |
|---|---|
| `Observation.live_sessions` field in `baselines/interface.py` | **absent** |
| `set(obs.live_sessions)` in `validate_action`'s `known_sessions` | **absent**; still the committed three-way union |
| `live_sessions=` in `cstate.CoordState.observation` | **absent** |
| any `live_sessions` reference in the tree | **one**: the tolerant `getattr(obs, "live_sessions", ())` already inside `engine_actions.known_sessions` |
| branches carrying the patch | none (`git branch -r` scanned) |

PATCH 1 of `study_engine_actions.md` section 3.1 has not landed, and its three edits are in
`interface.py` and `cstate.py`, both of which are outside this session's file ownership. This was
found by **Step 0, before a single sweep ran**, and it is exactly the asymmetry CLAUDE.md
describes: a minute spent before, against a null explained after.

**Consequence, and it is NOT the one that was expected, which is why Step 2b is run rather than
reasoned about.** `engine_actions.known_sessions` is still the committed three-way union, so a
MATERIALIZE is legal for a session that is already believed warm. **An arm that builds histories
therefore creates its own candidates.** Measured, not inferred:

| arm | warm-ahead fetches WANTED | refused by `validate_action` | EMITTED legally | extra prefills ISSUED over its own base |
|---|---|---|---|---|
| `attentionstore-prefetch` | 47,626 | 45,692 (**95.9 %**) | **1,934 (4.1 %)** | **+19** (393 against 374) |
| `kvflow-prefetch` | 8,600 | 8,600 (**100 %**) | **0** | **0** (0 against 0) |

So the blocker is real, it is binding on **95.9 %** of attentionstore's wants and on **100 %** of
kvflow's, and **it is not total**. `attentionstore` is the one arm in this family that already
builds histories reactively (34,191 state actions and 374 whole builds at this cell), so some of
its sessions do reach GPU-warm, and a warm-ahead fetch for one of those is legal today.
**`attentionstore-prefetch` therefore passes all four proofs on the committed harness and is
scoreable now**; `kvflow-prefetch` is `unexpressible` and is not. Had this study reported the
blocker from the source and stopped, it would have labelled a passing arm as mute.

Every proof is still run in **both** conditions, reusing `arms_warmall`'s own reviewed in-process
shim of PATCH 1, so the size of the blocker is *measured* rather than argued. **The shimmed
column is labelled `shimmed`, is a different regime (1,402,698 decisions against 48,135), and is
not evidence about the committed harness.** Zeros in the committed column are **unexpressible**
under CLAUDE.md Rule 2, never negatives and never findings about a published system.

---

## 1. The per-card audit, which decides what each baseline is entitled to

The card is the committed record of the adaptation (`arms_published.py`: "the card is the
committed record of the adaptation and the arm's behaviour is the thing under test"), so the card
decides. **Giving a baseline a capability its paper does not claim is as unfair as denying it one
it does**, in the opposite direction, and it is the easier mistake to make here because the
ruling asks for mechanisms to be *added*.

| baseline | card verdict | the card's own words | what it gets |
|---|---|---|---|
| **mooncake** | **NO** | "prediction-based early rejection policy"; "maximise KVCache reuse -> serve GPU-warm, then host-warm, then cold (`MOONCAKE-REUSE-FIRST` order) \| FAITHFUL in effect" | no arm. Both quoted mechanisms are triggered **by** a request. See section 2 |
| **attentionstore** | **YES** | "fetch for the sessions the **job scheduler** will run next, **not on demand at request time**", mapped `4.2 fetch -> scheduler_aware_fetch`, **FAITHFUL** | `attentionstore-prefetch`, section 3 |
| **preble** | **NO** | "trade cache affinity against load pressure"; "cross-GPU placement -- NOT REPRODUCED (one replica)" | no arm. Section 5 |
| **kvflow** | **YES** | "fully overlapped prefetch \| `prefetch` + `exposed_prefetch_s` \| **FAITHFUL in arithmetic**" | `kvflow-prefetch`, section 4 |
| **lmcache** | **NO** | "admission \| every session that asks \| FAITHFUL (LMCache caches by default)"; "in the suite as the **LRU contrast**" | no arm. Section 5 |
| **pensieve** | **NO** | "ahead-of-time swapping \| pipelined transfer overlapping computation"; A3: predicting reuse "would be a new policy, not Pensieve's. **FLAGGED**" | no arm. Section 5 |

**A SCOPE CAVEAT THAT TRAVELS WITH BOTH NEW ARMS, and it is not new to this study.**
`arms_published.OUT_OF_CARD_SCOPE` lists `attentionstore`, `kvflow`, `lmcache` and `pensieve` as
cards scoped to **B-recall only**, not to live2's C-mixed setting, and states the consequence:
"A row for an out-of-scope arm is not evidence about that published system in its own setting."
Four of the six baselines in this study are in that list, including **both** that get an arm. So
`attentionstore-prefetch`'s proofs establish that **the decision is now makeable and moves the
log**, which is a statement about our action space and is scope-independent. They do **not** make
any of these rows evidence about AttentionStore or KVFlow in the regime their papers claim, and
no number here should be cited as though they did.

This **revises `policy_v5_assessment.md` section I in four rows**. That table was a list of
candidates with a ruling requested, and it recorded "probably yes" for mooncake and "likely yes"
for kvflow, lmcache and pensieve. Read against the cards rather than against the papers'
reputations, only two of the six publish a mechanism that creates cache for a request that has
not arrived.

---

## 2. mooncake, which was first in the user's order and gets no arm

### 2.1 The card's claim, quoted in full

`cards/mooncake.md` contains exactly two mechanism claims:

> "Unlike traditional studies that assume all requests will be processed, Mooncake faces
> challenges due to highly overloaded scenarios. To mitigate these, we developed a
> **prediction-based early rejection policy**."

> "its architecture maximises KVCache reuse across a disaggregated prefill/decode pool"

mapped as:

| Mooncake | our code | note |
|---|---|---|
| prediction-based early rejection | `REJECT` when the predicted TTFT exceeds the slack **and** the replica is overloaded | FAITHFUL |
| maximise KVCache reuse | serve GPU-warm, then host-warm, then cold (`MOONCAKE-REUSE-FIRST` order) | FAITHFUL in effect |

and the card's "Not reproduced" section disposes of the rest: "The disaggregated architecture;
**the transfer engine and its storage tiers**; the TBT SLO; the paper's throughput results."

**The ruling.** Early rejection is a per-request admission test at the moment a request arrives.
Reuse-first is an ordering over requests that have arrived. Neither creates cache for a request
that has not arrived, and the transfer engine, which is where any prefetch would live, is
explicitly not reproduced. Section I's reason for "probably yes" was that cache-centric
scheduling is "the closest published analogue to warm-ahead". **An analogy is not a claim.**
Mooncake gets no warm-ahead lever, its committed cells are unaffected, and they need no
relabelling, because no proactive mechanism was withheld from it.

### 2.2 What the audit measured instead, and it is stronger than the ruling

Section I's mooncake row reads "reactive only; 0 gpu beliefs, 0 engine prefix hits in its
committed cells", which describes the **outcome**. CLAUDE.md Step 2 asks a different question: is
mooncake's reuse mechanism a live causal link at all? Measured, seed 4, 16 devices, 1200 s,
`40:40:20`, `lh_req`/`ss2`, DRY:

| quantity | measured | what it means |
|---|---|---|
| epochs | 12,001 | |
| session actions emitted | **`KEEP_GPU_WARM` 377, and nothing else** | `OFFLOAD_TO_HOST` never fires, because `known` is drawn from `obs.recall` only, so mooncake names no session that is not already asking |
| recall readiness at first sight | **`COLD` 377 of 377** | |
| distinct readiness values over the whole run | **1** | the reuse-first sort key is a constant |
| `max(len(obs.cloud.gpu_warm_sessions))` over 12,001 epochs | **0** | |
| `max(len(obs.cloud.host_warm_sessions))` over 12,001 epochs | **0** | there is no warm tier to be first about |
| distinct sessions asked | 374 | |
| ask-count histogram | **371 sessions ask once, 3 ask twice** | 0.8 % repeat traffic |
| readiness by nth ask | ask 1: `COLD` 374; **ask 2: `COLD` 3** | even the repeat asks are cold, so retention did not hold across a turn either |
| `SessionRec.set_tier` calls | **0** (second probe) | no session ever changed tier; the 377 keep-warm actions resolve to a `last_touch_s` refresh in `cstate.enact_placement` and nothing else |
| decision kinds | `release_monitor` 13,193, `state_action` 377, `release_recall` 372, `decline` 5 | |

Two independent probes, written separately, returned the same counts.


**The causal chain and where it breaks.**

> KVCache reuse -> `MOONCAKE-REUSE-FIRST` order -> which recall is served first -> more reuse,
> lower TTFT, more on-time answers.

`MooncakeAdapted.decide` sorts by `{"GPU-WARM": 0, "HOST-WARM": 1, "COLD": 2}[q.readiness]` and
then by deadline. **Every query is COLD in every epoch**, so the first sort key is the constant
`2` and the reuse-first order degenerates to deadline order, which is `b7-edf-feasibility`'s
order. The implementing quantity is **CONSTANT**, which is a CLAUDE.md Step 2 stopping condition
in its own right, and it is independent of the prefetch ruling.

This completes a finding the D130 port note had only half of. That note established the
**channel** half -- `coordinator.py` never reads `Action.order`, so even a varying order could
not reach a decision -- and recorded the measured convergence of mooncake and b7 as "a result
about the regime". This audit adds the **signal** half: the order mooncake computes is identical
to b7's before the channel ever discards it. The convergence is not a coincidence of the regime;
it is arithmetic.

`cstate.py:428` records the same thing from the other side at 10 devices: "every session stayed
`cold` and mooncake's 10 KEEP_GPU_WARM actions therefore had nothing to act on." This run is the
16-device, 1200 s version of that sentence.

**The second reason, which the first does not need.** 371 of 374 sessions ask exactly once, and
the three that ask twice are `COLD` on the second ask as well. Mooncake is a multi-turn KVCache
reuse architecture, and this fleet offers it 0.8 % repeat traffic with nothing retained across
the gap. So mooncake's reuse mechanism is **CONSTANT** in its signal *and* **unexercised** in its
workload, and neither is fixed by giving it a prefetch it does not claim. **That is the finding
to carry into any v5-versus-mooncake headline:** when mooncake and b7 converge, it is not because
two distinct schedulers happened to agree, it is because mooncake's distinguishing input never
varies.

**What would change it.** A warm tier that is ever non-empty, which is what `warm-all-lru` and
`attentionstore-prefetch` exist to produce. Once some session is GPU-warm, mooncake's sort key
varies and the Step 2 stopping condition lifts -- and the D130 note's channel half becomes the
binding blocker instead, because `coordinator.py` still never reads `Action.order`. **Mooncake
therefore needs two fixes it cannot make itself, and neither is a prefetch.**


### 2.3 A note the citing rules need, because mooncake PASSES the port proof while doing nothing

`baseline_prescreen.DECLARED` names mooncake's characteristic decision as `state_action`, on the
correct grounds that "mooncake [exists] to retain state". Its `state_action` count at this cell is
**377**, comfortably non-zero, so **mooncake passes the port-side proof CLAUDE.md requires** --
"record the count of the decision kind that arm exists to make, and confirm it is non-zero" --
and it passes it while its retention changes nothing: every one of those 377 actions names a
session whose belief is `COLD`, `set_tier` is never called, and `cstate.enact_placement` resolves
a keep-warm on a cold session to a `last_touch_s` refresh.

This is not a defect in the port proof; it is the proof's stated limit meeting a case it cannot
see. The rule catches an arm that makes **zero** decisions of its kind. It cannot catch an arm
that makes **377** decisions of its kind on a quantity that is constant, because a non-zero count
is exactly what it asks for. **The missing check is Step 2's, applied to the input rather than
the output:** confirm the quantity the decision reads varies across the conditions where the
claim says it should. A count of actions emitted and a count of decisions moved are different
registers, and `state_action = 377` is the first.

---

## 3. attentionstore, the baseline most disadvantaged by the action space

### 3.1 The card's claim

`cards/attentionstore.md`, the paper's algorithm table:

> | scheduler-aware fetching | 4.2 | fetch for the sessions the **job scheduler** will run next,
> | not on demand at request time. |

mapped `4.2 fetch -> scheduler_aware_fetch`, marked **FAITHFUL**, and named first in the card's
own summary of what survives adaptation: "what the policy uses is scheduler-aware fetching and
eviction, which is what the paper fundamentally decides." The reconstruction repeats it verbatim:
"the cache of a session about to be scheduled is fetched first, instead of fetching on demand at
request time." **There is no ambiguity in this card.**

### 3.2 Why the committed adapter does the opposite, and it is not the adapter's fault

The card's ADAPTATION A3 proxies "the scheduler's queue" with "our recall queue in deadline
order", and `AttentionStoreAdapted.decide` builds that queue out of `obs.recall`:

```python
queue = [q.session_id for q in sorted(obs.recall, key=lambda x: x.deadline_s)]
```

`obs.recall` is questions that have **already arrived**. So the committed arm fetches exactly **on
demand at request time**, which is the one thing section 4.2 is defined against. A3 was the only
reading available while warming ahead was unexpressible.

### 3.3 What was implemented

`attentionstore-prefetch`, a **new labelled arm**. The committed `attentionstore` adapter, card
and cells are untouched; the committed cells are relabelled `no-prefetch` and queued for rerun.

* The queue handed to `scheduler_aware_fetch` is widened from "sessions with a pending question"
  to "sessions the scheduler holds", which in live2 is the D100 open-session roster
  (`session_device`): a causal fact, known at arrival, read nothing of the future.
* `scheduler_aware_fetch` is the paper's own reconstructed function, called **unchanged**, with
  the card's committed `gpu_warm_slots = 4`.
* **The widened queue's order is the narrow reading, deliberately.** Section 4.2 reads a queue
  the scheduler *knows*; it does not predict who will ask next. Predicting that from observed
  inter-arrival history is **KVFlow's** mechanism, and handing it to AttentionStore would give
  this baseline a capability its paper does not claim. So the tail is ordered by the paper's own
  stated tie-break, "least-recently-used, which is the paper's fallback when the scheduler has no
  opinion", and by nothing else. **Pending sessions keep their deadline order and come first**, so
  A3's committed reading is preserved as the head of the queue rather than replaced.
* One MATERIALIZE, `slice_tokens=None`, because the card records that "the paper loads a whole
  prefix".
* Emission is routed through `engine_actions.plan_warm_ahead`, which drops any session with a
  pending question by construction and reports `unexpressible` separately from `legal`, so a
  reactive fetch can never be summed with a prefetch and a harness refusal can never be read as a
  policy decision.

**ADAPTATION A5, new and stated rather than silent.** The prefetch yields to deadline work (W2,
D143 ruling B). That discipline is the harness's, not the paper's: section 4.1's fetch is
asynchronous and layer-overlapped and preempts nothing, and live2 has no asynchronous prefill, so
a background MATERIALIZE that did not yield would take a slot from a request already under a
deadline. `attentionstore-prefetch-noyield` exists so the claim is checkable, and is in no run
plan.

### 3.4 What it still does not do

Layer-wise pre-loading and the disk tier (card A1) remain unexpressible and were not attempted.
Positional decoupling stays a predicate. The eviction rule is the committed adapter's
`scheduler_aware_evict`, untouched: this arm adds a fetch channel and nothing else, which is what
makes its Step 2b diff readable as the fetch channel.

### 3.5 The four proofs

Cell: seed 4, 16 devices, 1200 s, `40:40:20`, `lh_req` / `ss2`, **DRY** (stub bridge, no engine).
Artefact: `results/orchestration/live2/kv_prefetch/attentionstore_prefetch_proofs.json`.

**Consistency check 7, the POSITIVE CONTROL, first, because nothing below may be read if it
fails.** The base arm must reproduce its own behaviour in this harness. Committed `attentionstore`
at this cell: **48,135 decisions**, `release_monitor` 13,193, `state_action` 34,191,
`release_recall` 377, `release_whole` 374, `piece_split` 374, `desired_tier_set` 34,191,
representations `D2` 377 and **0 non-default**, `decline` 0, `defer` 0. This is a state-management
arm that steers placement on every epoch and takes the documented default representation, which
is exactly what `cards/attentionstore.md` declares (`defaults_used` includes `representation`;
`decides` includes `session_action`). The control reproduces it **byte-identically** (proof 2), so
the harness is sound and the bar is the arm's own.

| # | proof | committed harness | PATCH 1 shimmed |
|---|---|---|---|
| 1 | **well-formedness** | completed, **0 illegal actions**, 50,843 decisions | completed, 0 illegal, 1,402,698 decisions |
| 2 | **fairness digest vs its own committed version** | base `b09ce0cc04cd6bec` (48,135 decisions); control `attentionstore-prefetch-off` **`b09ce0cc04cd6bec`, byte-identical on the decision rows**; treatment `ad6def3999fdedd3` | treatment `88f5b6120f06ab8b` |
| 3 | **characteristic decision** -- a MATERIALIZE for a session with **no pending question** | **1,934 emitted** (asks), of 47,626 wanted, 45,692 refused; **+19 prefills ISSUED** (393 against the base's 374) | **39,855 emitted**, 0 refused; **+571 prefills issued** (945 against 374) |
| 4 | **Step 2b decision diff vs base**, setwise | **2,708** | **1,371,757** |

**VERDICT: PASS on the committed harness, all four.** Zero illegal actions; the control collapses
to the committed base byte-identically; the characteristic decision occurs 1,934 times and issues
19 prefills the base does not; and the switch moves 2,708 decisions.

**REGISTER, marked at the point of use, because two of those numbers are in different ones.**
`1,934` and `39,855` are **asks**: one MATERIALIZE emitted per promoted session per epoch, and a
standing request for a session with nothing newly uploaded is a **no-op** inside
`coordinator._advance_build` (`new_refs` empty returns None). `393`, `374` and `945` are
**observed counts** of `release_piece` / `release_whole` rows in the coordinator's own decision
log: prefills the coordinator actually issued. **The headline is +19, not +1,934.** This is the
same register trap `arms_warmall` section 4.1 records, where 91,592 asks corresponded to 77
issued prefills, and it is why the count is read off the log rather than off the arm.

**Where the 1,934 legal fetches come from, stated because it is the mechanism and not a loophole.**
Committed `attentionstore` builds histories reactively, so some of its sessions reach GPU-warm and
enter `known_sessions`. A warm-ahead fetch for a GPU-warm session is legal today. It is still a
fetch **ahead of a question** -- `plan_warm_ahead` drops every session in `obs.recall` by
construction -- so it is the characteristic decision and not a reactive one in disguise. What
PATCH 1 would add is the other 95.9 %: the sessions that have never been built, which is where
the paper's own mechanism mostly lives.

**The 1,402,698-decision shimmed column is a DIFFERENT REGIME and must not be read as a bigger
version of the same thing.** With every held session nameable, a standing fetch for the whole
roster turns into a 29x increase in decisions, which is what `warm-all-lru` is for and what
`study_frozen_test.md` 16.3 point 5 warns about for W1. Nothing here says that regime is good.

---

## 4. kvflow, whose prefetch is on its card and has nothing to fire on

### 4.1 The card's claim, and the trigger it already supplies

`cards/kvflow.md` maps "fully overlapped prefetch" to `prefetch` + `exposed_prefetch_s`, marked
**FAITHFUL in arithmetic**. The paper's core signal, steps-to-execution off a known workflow
graph, is forbidden here under fairness rule 5, and **the card resolves that rather than dropping
it**: the adapted policy "ESTIMATES steps-to-execution from each session's OWN observed
inter-arrival history - an exponentially-weighted mean gap, turned into expected seconds until the
next arrival". `KVFlowAdapted._steps_to_execution` is that estimator, it is committed, and it is
used **unchanged** here. No new predictor was added. The card's warning travels with every number
below: "KVFlow's advantage over LRU comes from exact future knowledge; a causal estimate is
strictly weaker, and any result must say so."

### 4.2 Why the committed adapter cannot prefetch, although it calls `prefetch`

`KVFlowAdapted.decide` builds its node set from `obs.recall` plus the two warm-session lists.
**Both warm lists are empty in every epoch on this fleet**, so the node set is exactly the pending
questions and `prefetch` can only ever name a session that is already asking. The `materialize`
it emits was legal precisely because the session was pending, which is why this fault never
raised and never appeared as an illegal action. Its own card-claimed mechanism was dead.

### 4.3 What was implemented, and the prediction recorded before the run

`kvflow-prefetch`, a **new labelled arm**. The node set is widened to the sessions the cloud holds
frames for; `evict` and `prefetch` are the paper's own reconstructed functions called unchanged
with the committed `gpu_capacity_tokens`, `prefetch_horizon_s` and `slots=2`; only sessions the
base did not already name and that have no pending question are added, through
`plan_warm_ahead`.

**Step 0, pre-registered in the arm's own docstring before the run:** `_steps_to_execution`
returns `inf` for a session never seen twice, and `prefetch` selects on a finite horizon, so a
fleet of single-ask sessions gives this lever nothing to fire on **even with the channel open**.
Section 2's audit measured 371 of 374 sessions asking exactly once. If the count is near zero the
correct classification is **unexercised**, not a negative.

### 4.4 The four proofs

Cell as above. Artefact:
`results/orchestration/live2/kv_prefetch/kvflow_prefetch_proofs.json`.

**Consistency check 7, the positive control, first.** Committed `kvflow` at this cell:
**13,947 decisions**, `release_monitor` 13,193, `state_action` 377, `release_recall` 377,
`desired_tier_set` 377, representations `D2` 377 and **0 non-default**, `piece_split` **0**,
`release_whole` **0**. So the committed arm issues **no build at all**: its `materialize` branch
requires a node that is in `after` and not resident and in `pull`, and `pull` is empty because
`prefetch` needs a finite `steps_to_execution`. **kvflow's card-claimed prefetch was already dead
in the committed arm, and this is the first measurement of that.** The control reproduces the base
byte-identically (proof 2), so the bar is the arm's own.

| # | proof | committed harness | PATCH 1 shimmed |
|---|---|---|---|
| 1 | **well-formedness** | completed, **0 illegal actions**, 13,947 decisions | completed, 0 illegal, 15,135 decisions |
| 2 | **fairness digest vs its own committed version** | base `7fa6b4aa9a9dd9c6`; control `kvflow-prefetch-off` **`7fa6b4aa9a9dd9c6`, byte-identical**; treatment **`7fa6b4aa9a9dd9c6`, also identical** | treatment `786e5878b0337f52` |
| 3 | **characteristic decision** | **0 emitted**, of 8,600 wanted, **8,600 refused (100 %)**; **0 prefills issued**, base 0 | **5,120 emitted**, 0 refused; **87 prefills issued**, base 0 |
| 4 | **Step 2b decision diff vs base**, setwise | **0 -- ABSENT LINK** | **9,698** |

**VERDICT: proofs 1 and 2 pass; proof 3 and proof 4 FAIL on the committed harness.** The treatment
digest equals the base digest exactly, which proof 2's own note calls out in advance as the
signature of an absent link. Under CLAUDE.md Rule 2 this is **unexpressible**: the mechanism fires
8,600 times and `validate_action` discards every one. **It is not a negative, it is not evidence
about KVFlow, and `kvflow-prefetch` must not be scored until PATCH 1 lands.**

### 4.5 The pre-registered prediction was REFUTED, and the thing it was about is still true

Section 4.3 pre-registered, before the run, that the estimator would give this lever nothing to
fire on and that the result would be **unexercised**. Measured: with the channel open it fires
**5,120** times and issues **87** prefills. **The prediction was wrong on magnitude.** Recorded as
refuted rather than quietly dropped, because a prediction that only ever gets confirmed is not
doing any work.

**What the prediction was about is nonetheless confirmed, and sharper than predicted.** Measured
directly, on the shimmed run:

| quantity | value |
|---|---|
| distinct sessions ever prefetched | **3** |
| sessions in the fleet | **374** |
| **mixing weight** | **0.8 %** |
| the 3 sessions | `robo002\|s001` 3,172 asks, `robo003\|s001` 1,877, `robo004\|s000` 71 |
| sessions asking twice at this cell (section 2.2) | **3** |

**The three sessions the prefetch fires on are exactly the three sessions that ask twice**, and
that is not a coincidence, it is the estimator: `_steps_to_execution` returns `inf` unless
`self._gap[sid]` exists, and `_gap` is written only when a session appears in `obs.recall` with a
previous appearance already recorded. One ask, no gap, no finite horizon, no prefetch, for ever.
Once a gap does exist, `max(g - (now - last), 0)` decays to 0 and stays there, so those three
sessions are prefetch candidates in **every remaining epoch** -- which is where 3,172 and 1,877
come from. The lever is not weak; it is **all-or-nothing per session, and on this fleet it is
"nothing" for 371 of 374.**

**So 87 prefills is a number with a stratum of three, and CLAUDE.md check 3 requires the mixing
weight beside it rather than under it.** Any future kvflow-prefetch cell must report the stratum,
because a population mean over 374 sessions would read as a tiny uniform effect when it is a
total effect on 0.8 % of them. And the card's own warning is the right frame: KVFlow's advantage
"comes from exact future knowledge", and a causal estimate that needs two observations to produce
one prediction is strictly weaker on a workload where almost nothing is observed twice.

**kvflow is therefore blocked twice, independently**, and removing PATCH 1's blocker does not
touch the second: the workload. P17 and P18 in the design log are where that would change.

---

## 5. preble, lmcache and pensieve: no proactive mechanism on the card

No arm was written for any of these, and no committed cell of any of them needs relabelling,
because nothing was withheld from them.

**preble.** `cards/preble.md` is explicit that what survives its adaptation is a **principle**:
"What survives is the **principle** -- trade cache affinity against load pressure -- and that is
what this baseline implements." Its mapping has no fetch and no prefetch: affinity is a readiness
term, the co-optimised score "order[s] the queue", and "cross-GPU placement" is **NOT REPRODUCED
(one replica)**, as is "its prefix-tree matching, since our sessions do not share prefixes".
Preble's reuse is *placement and ordering of work that exists*. Section I already called this
"arguable: its reuse is placement, not prefetch"; against the card the answer is no.
**Note, and it is the same shape as mooncake's:** affinity is `1.0 / 0.5 / 0.0` by readiness, and
readiness is constant COLD on this fleet, so preble's affinity term is constant too and its
co-optimised score reduces to the load term alone. That is a Step 2 CONSTANT finding for preble
as well, and it is not fixed by a prefetch.

**lmcache.** `cards/lmcache.md` states what it decides: "LMCache is a storage LAYER, not a
scheduler ... admit a session's KV, place it in a tier, and **evict by LRU** when a tier is
full", with admission "every session that asks" marked FAITHFUL because "LMCache caches by
default". Caching what asks is not prefetching what has not. The card also states its role:
"LMCache is in the suite as the **LRU contrast** to AttentionStore's scheduler-aware eviction and
Pensieve's value-ordered one, so that the three state-management baselines differ only in their
eviction rule." **Giving lmcache a prefetch would delete the contrast the suite is built on**, and
would make the three state-management baselines differ in two things instead of one. Section I's
"likely yes" cannot survive that sentence.

**All three share one structural fact, and it is worth stating because it shows the problem is
the action space and not the adapters.** `lmcache_adapted.py`, `pensieve_adapted.py` and
`preble_adapted.py` each build their candidate set as `gpu_warm_sessions | host_warm_sessions |
{q.session_id for q in obs.recall}` -- `interface.validate_action`'s own `known_sessions`,
copied. Two of them already emit `materialize` for a session they want warm. So the *action* was
always available to them; the *candidate* never was, because the only sessions they could name
were the ones already asking. The widening in section 3 is the same one line for all six. The
cards are what decide which three should get it.

**pensieve.** `cards/pensieve.md` does list "ahead-of-time swapping", but the card says what it
is: "§4 | pipelined transfer overlapping computation", mapped to `aot_swap_s`, a **cost-model
term** for overlapping a transfer with compute for work already in hand. It is not a decision to
warm a session that has not asked. The card then forecloses the alternative itself, in **A3**:
"The paper's 'attractive for longer' implies a reuse estimate; we expose one constant
(`reuse_horizon_s`, 30 s) rather than predict it, **because predicting reuse from our observation
would be a new policy, not Pensieve's. FLAGGED**." Adding a predictive prefetch to pensieve is
precisely the thing its card already refused. What pensieve's card *does* justify is retention
ordering, which `touch` expresses and which its adapter already emits.

---

## 6. Mechanism verification, Steps 0 to 5, recorded before any sweep

**Step 0 -- what would make this run uninterpretable, asked before starting it.**

| question | answer | cost |
|---|---|---|
| Is the channel the mechanism acts through actually open? | **WAIT.** PATCH 1 is not on origin (section 0), contrary to the brief. The run proceeds in two labelled conditions rather than one, which is what let the 4.1 % that IS expressible be found rather than assumed away. | one `grep`, one minute |
| Is the comparator about to change? | No. The committed adapters are untouched by this work and no committed arm's behaviour moves. | |
| Does the mechanism have a reachable path in this regime? | attentionstore: **expected only once the channel is open**; measured partly reachable WITHOUT it, 4.1 % of wants, because the arm builds its own warm candidates. kvflow: **predicted no** (single-ask fleet), recorded in the arm's docstring before the run; measured as 100 % refused on the committed harness and, under the shim, firing on 3 of 374 sessions. mooncake: n/a, no arm. **Both Step 0 predictions were wrong in magnitude and both are recorded as refuted.** | |
| Is a default about to be restored? | No. Every new name is a new arm; no committed default is touched. | |

**Step 1 -- the causal chain.**

> If a published system's card claims it fetches KV for a session **ahead of** that session's
> request (`cards/attentionstore.md` 4.2; `cards/kvflow.md` prefetch row), then an adapter that
> can only name a session already in `obs.recall` cannot make that decision at all. Giving the
> adapter the open-session roster lets it name such a session; `plan_warm_ahead` turns that into
> a MATERIALIZE; `coordinator._advance_build` issues the prefill; the session's KV is resident
> before its question arrives; and the question no longer pays the materialisation inside its own
> deadline, which `study_frozen_test.md` 15.4 measured as edf's 5.483 s median wait against a 5 s
> deadline. The link under test in **this** study is only the first one: does the decision become
> makeable, and does it move the log. Nothing here scores on-time or quality.

**Step 2 -- each link instantiated, with the read that consumes it.**

| causal link | implementing quantity | value / range in this run | varies as expected? | the READ that consumes it |
|---|---|---|---|---|
| a card claims a fetch ahead of the request | the card text itself | 2 of 6 cards claim it (attentionstore, kvflow); 4 do not | yes, across baselines | section 1's audit; each arm's `live2_describe()["kv_prefetch"]["card_claim"]` |
| the arm can NAME such a session | `AttentionStorePrefetchArm._held_sessions()` / `KVFlowPrefetchArm`'s widened node set, from the D100 roster `session_device` | queue tail 2,289,180 session-epochs; node set widened by 2,289,180 | yes | `_scheduler_queue` (`arms_kvprefetch.py`, `AttentionStorePrefetchArm._scheduler_queue`), consumed by `scheduler_aware_fetch` |
| the paper's own rule selects from it | `reconstructed/attentionstore.py::scheduler_aware_fetch`; `reconstructed/kvflow.py::prefetch` | attentionstore 47,626 selected of 2,289,557 offered; kvflow 8,600 of 2,289,557 | yes | the return value is the `candidate_sessions` argument of `EA.plan_warm_ahead` |
| the selection becomes a legal action | `WarmAheadPlan.actions` / `.unexpressible` | attentionstore 1,934 legal / 45,692 refused; kvflow 0 legal / 8,600 refused | **yes for attentionstore, NO for kvflow** | `interface.validate_action`'s `known_sessions`, and then `coordinator._enact` |
| the action becomes a prefill | `release_piece` / `release_whole` rows | attentionstore **+19** over base (393 vs 374); kvflow **0** (0 vs 0) | **yes for attentionstore, ABSENT for kvflow** | `coordinator._advance_build` (`coordinator.py:435`, `:530`) |
| the prefill changes who is warm at question time | `RecallQuery.readiness` at release | **NOT MEASURED HERE** | -- | out of scope: a dry run has no engine, and `study_frozen_test.md` 16.1 puts the cost model 1.5x to 3.7x out on the warm side, so a dry run must not be asked what warming is worth |

**The last link is deliberately left unmeasured and is marked so, rather than estimated.** This
study's claim is that the decision becomes makeable and moves the log. It makes no claim about
on-time or quality, and no number here may be cited for one.

**kvflow's fourth and fifth links are ABSENT on the committed harness**, which under CLAUDE.md is
a stopping condition for scoring it: `kvflow-prefetch` is not scored and no kvflow row is
written.

**Step 2b -- the switch reaches a decision.** Run on one cell, before any scoring, in both
conditions: see the proof-4 rows in sections 3.5 and 4.4. The committed-harness diff for
`attentionstore-prefetch` is reported beside the shimmed one and the two are never added.

**Step 3 -- one representative unit.** One unit, from the shimmed `attentionstore-prefetch` log, chosen because it is the FIRST
differing row and therefore not selected for being favourable:

```
t = 0.1 s                    (the first epoch of the run; no question has arrived anywhere)
kind = release_whole
note = session=robo000|s000|1011205677616862_start_0.0_end_314.103
piece_tokens = 301
representation_defaulted = false
belief = {gpu: {}, host: {}, cold: {}}      (nothing warm; this session has never been built)
traffic_mix = {monitor: 0, piece: 0, recall: 0, whole: 0}
```

Read it against the base's own log at the same cell, whose first row is
`kind = release_monitor, t = 5.1 s`. **This is the whole mechanism in one row.** At t = 0.1 s the
scheduler holds `robo000`'s session, that session has uploaded 301 tokens, no question for it
exists, and the arm prefills it. The committed `attentionstore` cannot produce this row: its
queue is `obs.recall`, which is empty at t = 0.1 s, so its first action of any kind is a monitor
release 5 seconds later. **The unit of this experiment is one fetch decision, and it is
recoverable, hand-checkable, and absent from the base.**

Charged costs, and what is NOT charged: `piece_tokens = 301` is the build charged to the GPU
path; no accelerator-ms and no KV-byte figure appears, because this is a dry run with a stub
bridge and the cost model is not engaged. Which budget bound the decision: **neither**, and the
reason is instrumented rather than assumed -- `prefetch_yielded_epochs` is absent from both arms'
stats, so `deadline_work_at_risk` was false in every epoch where a fetch was planned, i.e. W2
never had to yield at this cell. **That is a property of this cell, not a claim that W2 is
inert**; `attentionstore-prefetch-noyield` exists so the discipline can be tested where it does
bind.

**Step 4 -- negative control.** `attentionstore-prefetch-off` and `kvflow-prefetch-off` are the
same arms with the mechanism disabled. The requirement is stronger than "converges": each must
collapse to its committed base **byte-identically** on the decision rows with `arm_version`
stripped, because the coordinator writes that label into every row and a new arm necessarily
carries a new one. Results in the proof-2 rows.

**Step 5 -- the alternative explanation.** A non-zero prefetch count under the shim could be
produced by (a) the scheduler-aware fetch naming sessions ahead of their questions *[the claimed
mechanism]*, or (b) the arm simply emitting more MATERIALIZEs, which any arm with a wider
candidate set would do, including a round-robin over all sessions that reads nothing at all.
**The data distinguishes them, measured rather than argued.** A mechanism-free widening asks for
everything it can name: `warm-all-lru` does exactly that and its committed count is
**2,289,557 asks of 2,289,557 candidates, 100 %**. `attentionstore-prefetch` asks for
**47,626 of 2,289,557, 2.1 %**, because `scheduler_aware_fetch` is capped at
`gpu_warm_slots = 4` per epoch and selects by queue position; `kvflow-prefetch` asks for
**8,600, 0.4 %**, because its estimator gates on a finite horizon. Three arms on the same
candidate set, spanning 100 %, 2.1 % and 0.4 %, with each rate predicted by its own published
selection rule. **The selector is doing the selecting**, and explanation (b) would have produced
the same number for all three.

It is reported as a limitation that this study does not *score* the difference. `study_frozen_test.md`
16.1 states the cost model understates warm service by 1.5x to 3.7x, so a dry run must not be
asked what the prefetch is worth, and section 2's register line is the guard.

---

## 7. Results consistency check

Seven checks, in order. **Nothing below is a latency, throughput or size measurement**, so
checks 2 and 3's rate and distribution arithmetic have no quantity to bind on here and that is
recorded rather than skipped silently: every number in this report is a count of decisions from a
dry run with no engine.

**1. Cross-check against committed measurements.**

| quantity | this run | prior run | source of prior | ratio | agree? |
|---|---|---|---|---|---|
| warm-ahead candidate session-epochs at this cell | **2,289,180** (`queue_tail`, and `node_set_widened_by` independently) | **2,289,180** rejections | `reports/study_engine_actions.md` 4.1, `warm-all-lru` | **1.000** | **yes, exactly** |
| warm-ahead asks offered to the paper's selector | **2,289,557** | **2,289,557** asks | same | **1.000** | **yes, exactly** |
| `b7`-family feasibility actions at this cell | mooncake **5** declines | **5** | `reports/study_frozen_test.md` 13.4, b7 | 1.000 | yes (mooncake converges to b7's order, D130) |
| `release_monitor` rows at this cell | **13,193** for mooncake, kvflow and attentionstore alike | -- | this run, three independent arms | 1.000 | yes; the episodic stream is identical across arms, as it must be |
| mooncake session beliefs: any non-COLD | **0 of 377** | "every session stayed `cold` and mooncake's 10 KEEP_GPU_WARM actions therefore had nothing to act on" at 10 devices | `cstate.py:428` | -- | yes, qualitatively; the cells differ so no ratio is claimed |

**The first two rows are the strongest check available and they are exact.** `queue_tail` and
`node_set_widened_by` are computed by two different arms through two different code paths, and
both reproduce `warm-all-lru`'s committed candidate count to the unit, which establishes that
this is the same cell, the same trace and the same roster as the committed warm-ahead work.

**No disagreement exceeds 2x and none required explaining.** One number is deliberately NOT
compared: `warm-all-lru`'s 2,603 shimmed prefills against `attentionstore-prefetch`'s 945. They
are different arms with different selection rules (`warm-all-lru` asks for every session every
epoch; `scheduler_aware_fetch` caps at `gpu_warm_slots = 4` and orders by queue position), so the
difference is the selection rule and not a discrepancy. **Reporting it as a ratio would be the
artefact spread of CLAUDE.md check 3**: two credible numbers whose difference cannot mean what a
ratio column would say.

**2. Physical plausibility.** NOT APPLICABLE and stated so. No latency, throughput or byte
measurement is reported, no implied rate exists to compare against `results/cost/cost_matrix.csv`
or `reports/phase1_cost_profiling.md`, and no number here may be used as one. The register line
at the top of this report is the guard.

**3. Distribution sanity.** The one place a constant appears where a distribution might be
expected is mooncake's readiness, `COLD` 377 of 377, and **that constant is the finding, not an
artefact of it**: it is confirmed by three independent reads of the same run (the readiness
census, `max(len(gpu_warm_sessions)) = 0` over 12,001 epochs, and `set_tier` never called) and by
`cstate.py:428`'s prior record of the same behaviour at 10 devices. The spreads reported are the
arm-ask counts, and their register is marked at the point of use in every table: an ask is not a
decision, and the headline prefill counts are read off the coordinator's own decision log rather
than off any arm's statistics.

**4. Definition audit.**

| object | definition used in this run | prior committed definition | match? |
|---|---|---|---|
| **warm-ahead prefill** | a MATERIALIZE for a session NOT in `obs.recall`; counted as `WarmAheadPlan.n_warm_ahead` | identical; `engine_actions.py` and `arms_warmall.py` use the same function and the same exclusion | **yes** |
| **prefill issued** | a `release_piece` or `release_whole` row in `decision.jsonl` | identical; `arms_warmall` 4.1's `_piece_rows` | **yes** |
| **readiness** | the arm's BELIEF, which promotes only on a COMPLETE build (`cstate.SessionRec.set_tier`) | identical | **yes**, and labelled a belief everywhere it appears |
| **`gpu_warm_slots`** | 4 | 4, from StudyE10b's capacity table | **yes**, not re-tuned |
| **the cell** | seed 4, 16 devices, 1200 s, `40:40:20`, `lh_req` / `ss2`, `gpu_kv_tokens = 62,944` | identical to `arms_warmall.proofs()`'s cell and to D148's 62,944-token pool | **yes** |
| **"the scheduler's queue"** | pending recalls in deadline order, THEN the held sessions by LRU | `cards/attentionstore.md` A3: "our recall queue in deadline order" | **NO -- FLAGGED** |

**One name now carries two definitions and it must not be allowed to drift.** "The scheduler's
queue" means A3's recall queue in every committed `attentionstore` cell and the widened queue in
every `attentionstore-prefetch` cell. That is why the behaviour is a **separate labelled arm**
rather than a change to the committed one, why the committed cells are relabelled `no-prefetch`,
and why the widened queue **keeps A3's queue as its head** rather than replacing it: the two
definitions are nested, not rival, and the narrower one is recoverable from the wider one by
truncation. Any table that puts an `attentionstore` row next to an `attentionstore-prefetch` row
is comparing two definitions of the queue and must say so.

**5. Claim linkage, and it is the most consequential check in this report.**

The headline result bears on **C5**, "joint representation x placement x timing beats decomposed
policies under a quality SLO", and it bears on it through C5's own audit note rather than through
its evidence:

> "Its policies had disjoint single-point action spaces, so the comparison could not test
> coupling in either direction; those rows are marked INVALID and the 'coupling falsified'
> conclusion is withdrawn ... **Any future test must use policies that share a common action
> space.**"

That is the E24 defect, and this study measures the same defect in the live baseline suite. Our
offline P1 to P3 policies warm ahead of arrival and reach 65 of 65 robot questions at a 3 s
deadline against P0's 25 (`study_frozen_test.md` 15, 16, 19.4). The six KV-cache baselines
publish a mechanism in that same half of the action space and **could not name a session to warm
it**. So a v5-versus-baseline comparison on *timing* today is a comparison across action spaces
that do not contain each other, which is the condition C5's audit note forbids and the condition
`CLAUDE.md` records for E24b. **This weakens, and does not support, any existing timing advantage
read against attentionstore or kvflow**, and it does so without changing a single committed
number. For mooncake, preble, lmcache and pensieve the cards show the action spaces *do* match on
this axis, so those comparisons are unaffected by the prefetch question -- though mooncake's and
preble's own constant-signal findings (sections 2.2 and 5) limit what their rows mean for a
different reason.

Nothing measured here maps to C1, C2, C3, C4 or C6, and nothing here is scoped out by
`FORMULATION.md` section Scoping: no KV is moved between tiers running different-sized models,
and no cross-architecture KV transfer is measured or implied.

**6. Proxy validity.** Three proxies are in use and each is named at the point of use.
(a) **The open-session roster stands in for "the sessions the job scheduler will run next"**
(attentionstore card A3's proxy, widened). It actually measures "sessions the cloud holds
uploaded frames for". It is valid for the *expressibility* claim this study makes, and it is
**weaker than the paper's own signal**, which is a known queue: the paper knows the order, the
roster does not, which is why the tail is ordered by LRU and no predictor was added. It is
**not** validated for any claim about what prefetching is worth, and no such claim is made.
(b) **`RecallQuery.readiness` stands in for residency.** It is the arm's *belief*, which promotes
only on a complete build, and `coordinator.py:745-752` documents the gap: a partially built
history reads COLD while its prefix is reused on the wire. Every readiness count here is a belief
count and is labelled as one; the engine's own `cache_path` split is the different quantity and a
dry run cannot produce it.
(c) **The in-process shim stands in for PATCH 1.** It emulates both halves of the patch, the
observation carrying the live sessions and the validator accepting them, which is the failure
mode `study_engine_actions.md` 3.1 records from its own first attempt. It is **not** the patch,
and the shimmed column is not evidence about the committed harness.

**7. Validate the control, not only the result.** The positive control is the committed base arm
reproducing its own behaviour in this harness, reported first in every proof table, before the
comparison is read. The negative control is the `-off` arm, held to byte-identity rather than
convergence. Both are reported as numbers, not as assertions.

**The positive control that matters most here is the one that nearly was not run.** The
committed `attentionstore` base carries **34,191 state actions** at this cell. An arm that steers
placement on every epoch is a plausible-looking base, and it would have been easy to read the
treatment's `+19` prefills against a base assumed to make none. It makes **374**. Had the base's
own prefill count not been measured, `393` would have been reported as the arm's achievement
instead of `+19`, which is a **20x** overstatement in the only number the proof turns on. **Both
sides of every comparison in this report are measured and printed.**


---

## 8. What this does not do, and what is blocked

1. **No cell is scored and no leaderboard row is written by this study.** `attentionstore-prefetch`
   is *eligible* to be scored, because its characteristic decision occurs on the committed
   harness, but a dry run cannot produce the quantity a score needs. **What is unblocked is the
   scoring, not the score.**
2. **`kvflow-prefetch` may not be scored at all yet.** Its characteristic decision count on the
   committed harness is zero, its Step 2b diff is zero, and its treatment digest equals its base
   digest. CLAUDE.md's citing rule forbids scoring a port before its characteristic decision is
   shown to occur at least once in the condition being scored.
3. **PATCH 1 is still the dependency for 95.9 % of attentionstore's mechanism and 100 % of
   kvflow's**, and it is owned by someone else: its three edits are in `interface.py` and
   `cstate.py`, both outside this session's file ownership. This study does not apply it and does
   not recommend applying it without the byte-identity prescreen `study_engine_actions.md` 3.1
   specifies.
4. **Four of the six baselines get nothing**, on their own cards, and that is the answer to
   D155 (5) for them rather than a gap in this work. Two of those four (mooncake, preble) have a
   *separate* Step 2 problem -- a constant reuse signal -- which a prefetch would not fix and
   which this study measured for mooncake and derived for preble.
5. **kvflow is blocked twice, independently**: by the channel, and by a workload on which its
   estimator can never fire for 371 of 374 sessions. Removing the first does not touch the second.
6. **The committed `attentionstore` and `kvflow` cells are relabelled `no-prefetch`** and queued
   for rerun. They are not reinterpreted and not withdrawn. No committed adapter, card, arm or
   result file was edited by this work: `git status` in the worktree shows three ADDED paths and
   zero modified ones.
7. **No measured residency, latency, quality or capacity claim is made anywhere in this report**,
   and no number here may be cited as one.
8. **Nothing on the H100 or the Orin was touched**, no GPU was used, and seeds 1 to 3 and the
   holdout were not run: every cell is seed 4.

---

## 9. Draft rows for the files this session does not own

`research/EXPERIMENTS.md` and `results/INDEX.md` are outside this session's ownership, so the rows
are drafted here for the owner to apply.

**`research/EXPERIMENTS.md`, appended to the StudyV5-ENGINE verdict column:**

> **D155 (5), StudyKV-PREFETCH, 2026-11-20.** Of the six KV-cache baselines, only **two** publish
> a proactive mechanism on their own card: attentionstore ("fetch for the sessions the job
> scheduler will run next, not on demand at request time", FAITHFUL) and kvflow ("fully overlapped
> prefetch", FAITHFUL in arithmetic). mooncake, preble, lmcache and pensieve claim none, so
> `policy_v5_assessment.md` section I's "probably yes" / "likely yes" for those four is **revised
> to NO**, and their committed cells need no relabelling. `attentionstore-prefetch` **passes all
> four proofs on the committed harness** (0 illegal; control byte-identical to base
> `b09ce0cc04cd6bec`; characteristic decision 1,934 fetches ahead of a question and **+19**
> prefills issued, 393 against the base's 374; Step 2b setwise 2,708) and is scoreable; 95.9 % of
> its wants are still refused by `validate_action`, so PATCH 1 remains worth landing.
> `kvflow-prefetch` is **UNEXPRESSIBLE** (0 of 8,600 emitted, Step 2b setwise 0, treatment digest
> equal to base digest) and must not be scored. PATCH 1 is **NOT on origin at `55ec283`**,
> contrary to the brief. Separately, **mooncake's reuse signal is CONSTANT**: readiness is `COLD`
> in 377 of 377 queries over 12,001 epochs, `max gpu_warm_sessions = 0`, `set_tier` never called,
> so `MOONCAKE-REUSE-FIRST` is arithmetically identical to EDF before the D130 channel finding
> ever applies; 371 of 374 sessions ask once. Committed `attentionstore` and `kvflow` cells
> relabelled `no-prefetch`.

**`results/INDEX.md`, three rows:**

| file | script | model | device | n | headline | old name |
|---|---|---|---|---|---|---|
| `results/orchestration/live2/kv_prefetch/mooncake_card_audit.json` | `arms_kvprefetch.py` | none-dry | nvidia_rtx_a6000 | 16 | mooncake's card claims no proactive mechanism; its reuse signal is CONSTANT (COLD 377/377, 12,001 epochs) | -- |
| `results/orchestration/live2/kv_prefetch/attentionstore_prefetch_proofs.json` | `arms_kvprefetch.py` | none-dry | nvidia_rtx_a6000 | 16 | `attentionstore-prefetch` passes all four proofs on the committed harness: +19 prefills, Step 2b 2,708 | -- |
| `results/orchestration/live2/kv_prefetch/kvflow_prefetch_proofs.json` | `arms_kvprefetch.py` | none-dry | nvidia_rtx_a6000 | 16 | `kvflow-prefetch` UNEXPRESSIBLE: 0 of 8,600 emitted, Step 2b 0 | -- |
| `results/orchestration/live2/kv_prefetch/kvflow_prefetch_concentration.json` | probe, section 4.5 | none-dry | nvidia_rtx_a6000 | 16 | kvflow's prefetch fires on 3 of 374 sessions, a 0.8 % stratum | -- |

---

# Mooncake, resolved from the card AND the paper, because I said two different things

**The user is right that I contradicted myself.** An hour apart I listed mooncake among six baselines
publishing a proactive mechanism, then reported that its card publishes none. Neither statement was
right, and the resolution is sharper than both. Paper read at arXiv:2407.00079 (v5 HTML; §1 to §6
start verbatim, §6.1 onward from an extracted summary and marked as such below).

## What the paper actually publishes

**It DOES publish a proactive cache mechanism, and my first claim was not baseless.** Verbatim:

- §1.1: *"Conductor is also responsible for predicting the future usage of KVCache blocks"*, and
  *"executing scheduling operations such as swapping and replication accordingly."*
- §1.1: *"The hottest blocks should be replicated to multiple nodes to avoid fetching congestion"*;
  *"the coldest ones should be swapped out to reduce reserving costs."*
- §3: *"It also replicates or swaps certain blocks of the KVCache if it is beneficial for future
  inference."*

That last sentence is a mechanism acting on cache for inference that has **not arrived**, so a flat
"its card publishes nothing proactive" is wrong.

**But it is NOT warm-ahead of a session, and the paper itself undercuts the predictive reading.**
Verbatim, §1.2: *"a heuristic-based automated hot-spot migration scheme that replicates hot KVCache
blocks"* **"without requiring precise predictions of future KVCache usage"**. And the words
`prefetch`, `preload`, `speculative`, `warm up` and `ahead of time` appear **nowhere** in the
verbatim text read. Every per-request data movement is triggered on arrival: §1.1's
*"For each request, the global scheduler (Conductor) needs to select a pair of prefill and decoding
instances"* and then *"transfer as much reusable KVCache as possible to the selected prefill
instance"*; Algorithm 1's `FindBestPrefixMatch`.

So the published mechanism is **background hot-block REPLICATION and SWAP-OUT across nodes and
tiers**, not prefill of a session's history before its question arrives.

## Why it is unreachable here, which is the part both of my earlier claims missed

The mechanism is real and our harness cannot express it, for two **structural** reasons that are
nothing to do with PATCH 1:

1. **Replication needs more than one replica, and our adaptation has one.** The card's ADAPTATION A1
   maps *"disaggregated prefill/decode pools"* to *"one replica"*. With one replica there is no node
   to replicate a hot block TO, so the hotter half of the mechanism is inexpressible by construction.
2. **Swap-out needs a reachable slower tier, and the belief never reaches one.** `believed_tier` is
   `cold` or `gpu` and **never `host`** in 56 committed 16-device cells. So the colder half has no
   destination either.

The card's own "Not reproduced" section already disposes of the machinery both halves would live in:
*"The disaggregated architecture; the transfer engine and its storage tiers"*.

## The verdict, and it differs from both of my earlier statements

**Mooncake gets no warm-ahead arm, and the reason is not that its paper lacks a proactive mechanism.
The reason is that the proactive mechanism it does publish is cross-replica replication and
tier swap-out, and our adaptation removed the replicas while the belief never reaches the tier.**
That is an ADAPTATION consequence, which belongs in the card and in any fairness statement, not a
claim that the paper is purely reactive.

**Consequence for the rerun, reversing what I told the H100.** I suggested its mooncake rerun could
be dropped because there was nothing for `no-prefetch` to deprive it of. **That was wrong and the
rerun stays.** The label is accurate and the reason behind it is now a recorded limitation rather
than an absence: mooncake is compared in a harness that cannot express the proactive mechanism it
publishes, for reasons A1 and the unreachable host tier. That belongs beside any mooncake number,
and dropping the rerun would have removed the cell that the limitation attaches to.

**A second finding stands unchanged and is independent of all of this**: with readiness constant at
COLD in 377 of 377 cases, mooncake's reuse-first sort key is the constant 2, so MOONCAKE-REUSE-FIRST
is arithmetically identical to EDF in these cells. That is why its scores sit exactly on b7's.

**Register:** §6.1 onward was read as an extracted summary, not verbatim, so a claim of "no
pre-arrival prefetch anywhere in the paper" rests partly on that summary. The verbatim range (§1 to
§6 start) is enough to settle the question the card turns on, and the limit is stated rather than
hidden.
