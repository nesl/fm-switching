# StudyNET-QDELTA — does the absent question-time frame delta (D150 SYNC (2)) affect any committed main result?

Session on flash, 2026-11-23, under D150 / D166 / D213 / D216. **READ-ONLY, CPU ONLY.** No cell
was run, no server touched, nothing posted to the H100. `/proc/loadavg` at start 0.78, during the
sweep 1.68; the only other process on the box was another session's `gzip` housekeeping loop.
**No dry cell was needed, so the D216 (1) alone rule did not bind.**

Read sites, line numbers and cell contents are at the origin tip
**`b2d3d4b72ef4e83c6e61ea3127ed107650fb7bdc`**, resolved once and used for every read. Every byte
analysed was read with `git show <sha>:<path>`, never from the local checkout, which is over a
thousand commits behind and carries other sessions' uncommitted work.

A first pass ran at `3fa41f51`; origin moved during the session and the sweep was redone at the
tip. `arms_policy.py`, `cstate.py`, `arms.py` and `fleet/*` are **byte-identical between the two
shas**, so every line number below is unaffected; the tip adds one more cell at the tag
(`confidence-cascade s7 rerun`) and is what the numbers are computed on.

Script: `experiments/orchestration/live2/n4_question_delta_audit.py`.
Full per-cell output: `results/orchestration/live2/network/n4_question_delta_audit.json`.
Builds on `reports/study_network_tier1.md` and `results/orchestration/live2/network/*.json`
(Session N); nothing that report establishes is re-derived here.

---

## THE ANSWER IN ONE LINE

**The absent on-demand delta does NOT affect any committed main result.** Across **115 committed
main-operating-point cells** (1x memory, uniform link, seeds 4 to 7, 29 arm names, tag
`_L3_epg_rq30`) and **1,409,102 units**, there is **not one unit** in which the cloud's serving
request referenced a frame that had not finished uploading **by the time that request was
submitted**: **0 of 1,007,182** served units, worst-case margin **-2.364 ms** (the tightest unit
still cleared by 2.4 ms). The harness never let the cloud use evidence it did not hold, so there
is nothing a question-carried delta would have supplied.

**This is a real zero, not an absent instrument.** The same test fires elsewhere: 480 units are
late against the cloud-ask register and 1,388,958 against the device-ask register. The quantity is
instrumented, varies, and is non-zero in other registers; it is zero in the one that matters.

---

## 1. "Ask time" has three readings and the answer depends on which

This is the whole substance of the result, so it is stated before any number.

| register | definition | what a positive count would mean |
|---|---|---|
| `ask_device` | `t_opportunity`: the device's own capture / ask instant | the evidence had not finished its (charged) upload when the device asked |
| `ask_cloud` | the first instant the cloud can act: `t_frame_arrive` for a dashcam instant, the question's own arrival for a question | the cloud was handed the unit before some evidence it later used had landed |
| `ask_submit` | `t_submit` of the serving request | **the harness put a frame in a request before that frame had arrived** |

Only `ask_submit` can expose an unearned advantage. A positive count at `ask_device` is **not** a
defect: it is the push upload the emulator models and **charges** (D150 SYNC (1), every frame
uploaded as captured). All three are reported for every unit.

---

## 2. OBSERVED against CONSTRUCTED, marked at the point of use

**Committed cells DO record the frame completion time, per frame, for dashcams.** `t_arrive`
(`fleet/links.py:117`) is persisted onto the `Outcome` at `fleet/emulator.py:387` and `:407` as
`t_frame_arrive`, and written out at `fleet/emulator.py:621`. So:

| type | "references" is | completion time | register |
|---|---|---|---|
| dashcam instant | the serving request's literal `mm_uuids` (the EP-G episode's frames up to and including this instant, D148 / D153); for an instant the cloud never served, the episode frames charged at or before it | `t_frame_arrive` of the decision instant that **charged** that frame's bytes. `fleet/trace.py:519-536` charges every captured frame exactly once, at the first decision instant at or after its capture, so a sub-floor frame's bytes ride on the floor instant's upload | **OBSERVED** |
| robot recall question | the serving request's `mm_uuids`, i.e. the session-local D2 frame times the request actually carried | `t0 + x + serialise(24,570 B) + RTT/2`. `links.UplinkQueue.log` is **not** persisted per transfer (only `stats()` is), so this is reconstructed from the committed arithmetic: serialisation **plus FIFO queueing plus RTT/2**, never serialisation alone | **CONSTRUCTED** (the ask instant, the queueing term and `x` are OBSERVED; `t_ask` is the committed `sember_mcq.jsonl` `question_time`) |
| single-shot question | the one image `mm_uuid` | `t_opportunity + serialise(24,570 B) + RTT/2`, the image being offered at the question's own instant and **ahead of it** in the trace's record order (`fleet/trace.py:602-624`) | **CONSTRUCTED** (offer instant OBSERVED) |

**Per-type definition of "references".** Not a derived episode: the literal multimodal payload of
the request that served the unit (`request.jsonl` `mm_uuids`). For a dashcam decision instant that
is the EP-G episode's own frames up to that instant, which is the tighter question the brief asks
for; for a robot question it is the accumulated session history; for a single shot it is the one
captured image. Un-served units reference nothing and are counted separately.

**The session origin and the re-ask trap.** `t0 = t_opportunity - t_ask` is the session origin only
for a question's FIRST ask. These cells re-ask (`rq30`, "reask-device" in the cell label): in
always-cloud-fcfs seed 4 the 132 robot recall units come from **20** distinct (play, question)
pairs, one of them asked **16** times. Taking `t_ask` at face value for a re-ask placed frames up
to 402 s "after" the ask and produced 67 spurious hits in the first pass. `t0` is therefore the
minimum of that difference over the play, and the dispersion above the minimum is recorded per
cell as a diagnostic.

---

## 3. POSITIVE CONTROL, run before anything new was read

Three committed figures, each written by a different writer, recomputed from the very files this
module parses. **115 of 115 cells agree exactly on all three**, plus an independent fourth.

| figure | committed source | agreement |
|---|---|---|
| `n_devices` | `cell.json` score block | 115 / 115 exact |
| robot recall units | `cell.json` `robot_headline.n_by_deadline` | 115 / 115 exact |
| single-shot units | `cell.json` `assistive_value.n_cloud_standing + n_device_standing` | 115 / 115 exact |
| emulated uplink rate | D75 / Session N 13.6 Mbit/s | **13.6 Mbit/s in 115 / 115 cells**, derived independently (section 5.1) |

Two figures were deliberately NOT used as controls and the reason is recorded, because a control
that is not the same object is worse than none:

- `run_meta.completion_to_emulator_ms.n` counts cloud answers forwarded to the emulator, which
  differs from the rows of `request.jsonl` in **both** directions (attentionstore s4: 7,752 against
  8,168 rows; always-cloud s6: 8,340 against 8,322). Not the same object.
- `dashcam_value.n_plays` applies D85's exclusion of plays cut by the run end (183 committed
  against 189 play ids in `outcomes.jsonl` for always-cloud s4). A definition difference, not a
  parse error, so it is reported beside the controls and not as one.

---

## 4. THE RESULT: count, fraction and worst-case gap

### 4.1 By type, all 115 cells pooled

| type | units | evaluable | late at `ask_submit` | late at `ask_cloud` | late at `ask_device` |
|---|---|---|---|---|---|
| dashcam instant | 1,354,036 | 1,354,036 (964,677 cloud-served) | **0** | **0** | 1,354,036 (100 %) |
| robot recall | 13,988 | 9,088 served | **0** | 480 (5.28 % of served) | 1,505 (16.56 %) |
| single-shot | 41,078 | 33,417 served | **0** | **0** | 33,417 (100 %) |
| **total** | **1,409,102** | **1,007,182 served** | **0 (0.0000 %)** | **480 (0.0344 % of 1,396,541)** | 1,388,958 |

Worst-case gaps (how far past the ask time the latest referenced frame completed):

| register | worst gap | where |
|---|---|---|
| `ask_submit` | **-0.002364 s** (no unit is positive) | tightest unit, seed 4 |
| `ask_cloud` | +233.197546 s | `lmcache_n16_s7`, robo006, opp0006038 |
| `ask_device`, dashcam | +0.228593 s | a 3-frame floor-instant charge (3 x ~64 kB) |
| `ask_device`, single shot | +0.036453 s (constant) | every unit |
| `ask_device`, robot recall | +233.220252 s | the same unit as above |

### 4.2 Per arm (29 arm names; `late_sub` is the decisive column)

| arm | units | served | late_sub | late_cloud | worst gap at cloud (s) | late_device |
|---|---|---|---|---|---|---|
| always-cloud-fcfs | 49,012 | 32,793 | 0 | 6 | 0.072298 | 48,110 |
| attentionstore-prefetch | 49,012 | 31,876 | 0 | 21 | 230.551047 | 47,813 |
| b7-edf-feasibility | 49,012 | 37,938 | 0 | 1 | 0.042330 | 48,236 |
| confidence-cascade | 98,024 | 51,855 | 0 | 7 | 0.057633 | 95,510 |
| covex-v6-base | 12,252 | 10,363 | 0 | 1 | 0.082401 | 12,132 |
| covex-v6-fair-c5attr | 49,012 | 35,461 | 0 | 15 | 0.082401 | 48,591 |
| covex-v6-fair-c5attr-gain0 | 49,012 | 37,737 | 0 | 9 | 0.082401 | 48,584 |
| covex-v6-fair-c5attr-rr | 49,012 | 38,145 | 0 | 14 | 0.064828 | 48,591 |
| covex-v6-state | 36,769 | 17,718 | 0 | 6 | 0.071259 | 36,057 |
| covex-v6-state-shares | 49,012 | 38,834 | 0 | 7 | 0.644989 | 48,526 |
| covex-v6-state-shares-r1 | 49,012 | 39,922 | 0 | 14 | 0.651764 | 48,569 |
| covex-v6-state-shares-r2 | 49,012 | 41,007 | 0 | 19 | 0.846616 | 48,568 |
| covex-v6-state-uo | 61,264 | 45,210 | 0 | 17 | 0.082401 | 60,731 |
| covex-v6-state-uo-c5attr | 49,012 | 38,144 | 0 | 10 | 0.072298 | 48,584 |
| eco-llm | 49,012 | 40,807 | 0 | 6 | 0.050571 | 48,348 |
| edf | 49,012 | 32,034 | 0 | 130 | 2.878129 | 48,206 |
| hybrid-F-lhreq | 49,012 | 40,760 | 0 | 12 | 0.082401 | 48,591 |
| hybrid-F-lhreq-noc3 | 49,012 | 41,552 | 0 | 3 | 0.082401 | 48,552 |
| kvflow-prefetch | 49,012 | 33,172 | 0 | 9 | 0.671017 | 48,121 |
| llf | 49,012 | 42,696 | 0 | 66 | 1.999294 | 48,471 |
| lmcache | 49,012 | 32,872 | 0 | 42 | 233.197546 | 47,823 |
| mooncake | 49,012 | 41,053 | 0 | 1 | 0.093209 | 48,326 |
| querystream-proactive | 49,012 | 31,898 | 0 | 16 | 0.314564 | 48,090 |
| r3-streaming (superseded, D213) | 24,505 | 7,833 | 0 | 0 | 0.0 | 23,533 |
| simplestream | 49,012 | 48,981 | 0 | 15 | 0.082401 | 48,594 |
| streamscout | 49,012 | 48,958 | 0 | 13 | 0.082401 | 48,590 |
| v5-rules | 49,012 | 17,157 | 0 | 9 | 0.071259 | 48,584 |
| v5-rules-2 | 49,012 | 22,484 | 0 | 8 | 0.080549 | 48,568 |
| warm-all-lru | 49,012 | 27,922 | 0 | 3 | 0.042330 | 47,959 |

`r3-streaming` is reported because its cells carry this tag, and marked superseded under D213 so no
reader takes it for a paper-set arm.

### 4.3 Per seed

| seed | units | served | late_sub | worst gap at submit (s) | late_cloud | worst gap at cloud (s) |
|---|---|---|---|---|---|---|
| 4 | 355,337 | 244,316 | 0 | -0.002364 | 160 | 96.119586 |
| 5 | 379,812 | 266,392 | 0 | -0.002777 | 131 | 230.551047 |
| 6 | 343,392 | 244,433 | 0 | -0.003190 | 103 | 103.956537 |
| 7 | 330,561 | 252,041 | 0 | -0.002653 | 86 | 233.197546 |

### 4.4 The 480 units late at `ask_cloud`, and why they are not the bug

All 480 are **robot recall** questions, in **93 of 115 cells** (full list in the JSON under
`late_at_ask_cloud.units`). In every one of the 480 the referenced frame landed **before the
request was submitted**: the largest gap against `t_submit` is **-0.009039 s**. The submission sat
0.034 s to 289.082 s after the question arrived (p50 1.409 s), and a 2-s-stride history frame
landed inside that window.

- **282 of 480** had already missed the 3-s robot deadline, so the unit was a miss whatever
  evidence it carried.
- **198 of 480** were still within deadline. For these the request carried history **fresher** than
  at the ask instant by 0.015 s to 1.717 s (p50 0.051 s). That is the **opposite sign** to an absent
  delta: the harness gives the cloud slightly newer evidence, never older, and never evidence it had
  not received. 198 of 1,007,182 served units is **0.0197 %**.

Concentration by arm, which is what the mechanism predicts (the arms with the longest robot
queueing delays): `edf` 130, `llf` 66, `lmcache` 42, `attentionstore-prefetch` 21, then single
digits. Worst cells: `edf` s4 and s7 at 38 each, `edf` s5 36, `llf` s4 22.

### 4.5 Was there queueing at 13.6, and does Session N's constancy hold here?

Session N measured per-frame dashcam upload as **0.059587 s CONSTANT** across 2,420 frames and
asked that the constancy be verified rather than inherited. **It does not hold in these cells, and
that is correct, not a defect.** Session N's probe used the committed median frame size for every
frame; these cells read per-reference bytes from the Part-2 JPEG manifest, so the upload time is a
genuine distribution:

| quantity | this run | Session N / committed | ratio | verdict |
|---|---|---|---|---|
| dashcam per-frame upload, p50 | 0.059729 s | 0.059587 s | 1.0024 | agree |
| dashcam per-frame upload, min / max | 0.027117 / 0.228593 s, **15,196 distinct values** over 1,354,036 instants | constant by construction in N1 | — | distribution, as expected |
| dashcam uplink `queue_max` | **0.0 in 115 / 115 cells** | 0.0 at 13.6 (N1) | 1.0 | **no queueing at the main operating point** |
| robot / single-shot `queue_max` | 0.0 or **0.014453 s**, nothing else | serialise(24,570 B) = 0.0144529 s | 1.0000 | exact |
| 1,200 B question upload | 0.022706 s | 0.022706 s (N1) | 1.0000 | exact |

The 0.228593 s maximum is the D153 floor instant: `pending_b` folds the two sub-floor frames into
the third instant's upload, so one instant in each 21-frame episode cycle charges three frames.

**A constant where a distribution is expected, flagged.** The single-shot gap is **0.036453 s, one
value across all 33,417 units**, and its queueing term is **0.014453 s with zero spread**. This is a
real constant with a named cause, not short-circuiting: `ss2_questions` sets
`image_bytes = E10A_SEMBER_Q88_D2_MEDIAN_B = 24,570 B` for **every** question
(`fleet/data_sources.py:666`), so there is no input variation to carry. Same constant on the robot
side (`default_hist_frame_bytes`), which is why `queue_max` is identical across devices and cells.
The dashcam column beside it carries 15,196 distinct values, so the instrument is not collapsing
everything to a constant.

---

## 5. SECOND CHECK — the robot hard-coded link, and the downstream corruption, kept apart

### 5.1 Does the hard-code equal the emulated rate? YES, in every cell — but the site is never reached

`arms_policy.py:639` (at this sha, the brief's line number exactly):

```
f.add_device(self._device(did, 13.6e6 / 8.0, 0.044))
```

`13.6e6 / 8.0 = 1,700,000` and the emulated 13.6 Mbit/s is `13.6e6 / 8 = 1,700,000` bytes per
second. **Equal, in all 115 cells**, verified per cell rather than asserted:

An assistive device uploads nothing but (24,570 B image, 1,200 B question) pairs, both committed
constants, so `links.UplinkQueue.stats()["busy_s"]` pins the rate with no assumption:
`R = n_pairs x 25,770 x 8 / busy_s`. A robot is pinned the same way from its frame and question
counts. Over all 115 cells the implied rate takes exactly three values, **13.599999, 13.6 and
13.600001 Mbit/s** — 13.6 to within the float rounding of `busy_s`, which the artefact stores to 6
decimals. Worked example, always-cloud-fcfs seed 4, `asst000`: n = 238 transfers = 119 pairs,
committed `busy_s` = 1.803900 s; predicted `119 x 25,770 x 8 / 13.6e6 = 1.803900 s`. Exact.

**And the emulated rate really was 13.6 in every committed cell**, as Session N predicted from there
being no injection point: 115 of 115, no cell shows any other rate, and no cell shows dashcam
queueing.

**THE REGISTER ON THIS EQUALITY.** It is an **arithmetic** equality at a site that **no committed
main-operating-point cell executes**. `PolicyCoreArm`, the only class in `arms_policy.py` that is
ever built, is constructed at `arms.py:618` and `:623` for exactly three names: `policy-core`,
`covex-v13` and `policy-core-v13`. **None of the 29 arm names in these cells is one of them.** Every
other mention of `arms_policy` anywhere in `experiments/orchestration/live2/` is a comment or a
docstring (checked file by file: `cstate.py:254`, `engine_actions.py`, `hybrid/hybrid_arm.py:269`,
`v5/cf_objective.py:87-88,336`, `v5/value_readers.py:16`, plus the n1 / n3 / d211 / d213 probe
scripts). So the equality holds **and is unexercised**.

### 5.2 What actually reaches the planner's prediction after `:790` — 8x LOW, and on BOTH paths

Reported separately, because the source constant being right and the believed bandwidth being wrong
are two different statements.

```
arms_policy.py:788  def _device(self, device_id, uplink_bps, rtt_s):
arms_policy.py:790      link=Link(bandwidth_bytes_s=max(uplink_bps / 8.0, 1.0), rtt_s=...)
```

| | value |
|---|---|
| true uplink, emulated and committed | **1,700,000 B/s** |
| the source constant at `:639` | 1,700,000 — **correct, equal to the emulated rate** |
| what reaches `Link.bandwidth_bytes_s` after `:790` | **212,500 B/s** |
| error | **8x low**, consumed by `policy/coordinator.py:130-131` `dev.link.up_s(...)` into the predicted delay |

**One thing to add to the ruling: the dashcam path is corrupted identically.** `cstate.py:628` sets
`uplink_bps = uplink_mbps * 1e6 / 8.0`, which is already **bytes** per second (= 1,700,000), and
`arms_policy.py:631` passes that same value into the same `_device`, so it too is divided by 8 again
to 212,500. The 8x under-estimate is **not** specific to the robot literal: it lives in `_device` and
applies to every device entering the planner by either path.

### 5.3 Does D209 (2)'s NARROW scoping hold for the arms in this check? YES

D209 (2) ruled the `:790` bug narrow because the reported covex-v6 ladder never enters
`arms_policy.py`. **Confirmed for every arm in this check.** The 29 arm names present are
always-cloud-fcfs, attentionstore-prefetch, b7-edf-feasibility, confidence-cascade, covex-v6-base,
covex-v6-fair-c5attr, covex-v6-fair-c5attr-gain0, covex-v6-fair-c5attr-rr, covex-v6-state,
covex-v6-state-shares, covex-v6-state-shares-r1, covex-v6-state-shares-r2, covex-v6-state-uo,
covex-v6-state-uo-c5attr, eco-llm, edf, hybrid-F-lhreq, hybrid-F-lhreq-noc3, kvflow-prefetch, llf,
lmcache, mooncake, querystream-proactive, r3-streaming, simplestream, streamscout, v5-rules,
v5-rules-2, warm-all-lru. **No paper-set arm, and no rung of ours, enters `arms_policy.py`.** Nothing
to escalate on this item.

The scoping is contingent, not structural: it holds because of which names `arms.py` dispatches to
`PolicyCoreArm`, so it stops holding the moment `policy-core` or `covex-v13` is scored, or the moment
a per-device link is real (Session N's T2 note).

---

## 6. CLAUDE.md consistency checks

**1. Cross-check against committed measurements.** Table in 4.5. Every prior-measured quantity
agrees to within 0.24 %; the only intentional difference is the per-frame upload spread, whose cause
is named. Nothing disagrees by more than 2x.

**2. Physical plausibility.** The implied uplink is 13.6 Mbit/s = 1.7 MB/s in 115 of 115 cells,
identical to the committed curve, ratio 1.000. No result implies a rate faster than committed;
nothing to flag.

**3. Distribution sanity.** Spreads reported beside every quantile in 4.1 to 4.5. Two constants
flagged and explained in 4.5 (the single-shot gap and the queueing term), each with the named
committed constant that causes it. The dashcam distribution beside them (15,196 distinct values) is
the control that the pipeline is not collapsing distributions. No artefact spread: the completion
times are `t_arrive` values in seconds on the run clock, which is exactly what the column claims.

**4. Definition audit.** "references" defined per type in section 2 and tied to `mm_uuids`, the
request's literal payload. `t_ask` is the committed `sember_mcq.jsonl` `question_time`, and the
re-ask trap in these cells means that name does **not** give the ask instant for a re-ask; the
session-time ask used here is `t_opportunity - t0`, stated as such. Frame byte sizes: 63,897.5 B
(dashcam, E10a Nexar q90 median) and 24,570 B (robot history frame and single-shot image, E10a
S-EMBER q88 D2 median), both the committed constants; no second definition of either was found.

**5. Claim linkage.** This bears on D150 SYNC (2) and on the network term as D33 scopes it
("network cost is latency only"). It **supports** the committed main results being unaffected by the
absent delta. It does not speak to any Context Inertia claim, and measures nothing FORMULATION
scopes out.

**6. Proxy validity.** One proxy, declared: for robot and single-shot units the frame completion
time is **not** read from the artefact (the per-transfer `UplinkQueue.log` is not persisted) but
reconstructed from the committed arithmetic, with the FIFO term taken from the trace generator's
record order. It is validated against the artefact in two independent ways: the reconstructed
serialisation 0.0144529 s equals the OBSERVED `queue_max` 0.014453 s in every cell, and the OBSERVED
`busy_s` reproduces the committed rate exactly. For dashcam units no proxy is used: the completion
time is OBSERVED.

**7. Validate the control, not only the result.** Section 3. Three committed figures from three
different writers, 115 of 115 exact, plus an independently derived rate reproducing D75. Two
candidate controls were rejected with the reason stated, rather than used and silently disagreeing.

**Is the zero a real zero or an absent instrument?** **REAL.** `t_submit` and `mm_uuids` are
recorded on every served unit and `t_frame_arrive` on every dashcam instant, and the same comparison
returns 480 and 1,388,958 positives in the other two registers. A field nobody records cannot do
that.

---

## 7. Why it is zero — the mechanism, so the result is not just a count

For robot and single-shot units it is **structural, with a read site**: a frame enters the
coordinator's session record only in `cstate.py:336-341` (`history_append`, `s.frames.extend`),
which is invoked **only** from the emulator's `history_arrived` branch
(`fleet/emulator.py:509-523`), scheduled at `tr.t_arrive`. A request body can therefore only
reference frames that have already landed. For dashcam units it is the same shape one step earlier:
the `monitor_frame` event carrying the episode's `frame_refs` is forwarded at
`fleet/emulator.py:534-548` on the `frame_arrived` action, i.e. after the upload of this instant and
every earlier one has completed.

The FIFO ordering is what makes the simultaneous cases safe rather than marginal: evidence offered
at the same instant as a question is ahead of it in the trace's record order, so the question queues
behind its own evidence. That is visible in the artefact as the single non-dashcam `queue_max`
value, 0.014453 s, exactly one history-frame serialisation.

**Alternative explanation, and what distinguishes it.** The zero at `ask_submit` could be produced by
(a) the harness only ever referencing arrived frames [the claimed mechanism], or (b) the comparison
being vacuous because `t_submit` is always far later than everything. (b) is excluded by the margin:
the tightest unit clears by **2.364 ms**, and the `ask_cloud` register, which differs from
`ask_submit` only by the submission delay, produces 480 positives. A vacuous comparison would
produce zero in both.

---

## 8. Scope and what is NOT claimed

- **115 of 125** matching run directories were analysed; **10 are incomplete** in the committed tree
  (they carry only `frames_preflight.json`, `mm_gate.json`, `mm_uuid_check.json` and the stdout, with
  no outcomes or request log), and are listed under `skipped` in the JSON. All ten are the
  superseded half of a `_rerun` pair or an aborted cell. Nothing was inferred for them.
- `cascade-routing` and `device-only`, both in the D213 paper set, have **no cell at this tag**, so
  they are outside this measurement. `device-only` serves nothing from the cloud, so the question
  does not arise for it; **`cascade-routing` is a genuine gap** and should be covered when its cells
  land.
- This is a measurement over committed artefacts, not a policy experiment: no arm comparison is made
  and no verdict about any arm is implied. `r3-streaming` is included only because its cells carry
  the tag, and is marked superseded.
- Everything here is at the uniform 13.6 Mbit/s main operating point. Session N's T2 point stands:
  the moment a real per-device link exists, both the `:790` 8x error and the question-time delta have
  to be revisited, because at 0.9 Mbit/s a 16-device fleet saturates the uplink and a dashcam frame
  takes 6.34 s to land.

---

## 9. Proposed row text (owner's files, not edited here)

`results/INDEX.md`:

```
| results/orchestration/live2/network/n4_question_delta_audit.json | experiments/orchestration/live2/n4_question_delta_audit.py | - | cpu | 115 cells / 1,409,102 units | StudyNET-QDELTA: the absent D150 SYNC (2) question-time frame delta affects NO committed main result: 0 of 1,007,182 cloud-served units reference a frame that had not landed by t_submit (worst margin -2.364 ms); 480 (0.034 %) are late only against the cloud-ask register and every one landed before submission; robot hard-code 13.6e6/8.0 EQUALS the emulated rate in 115/115 cells but the site is unreached by all 29 arms, while arms_policy.py:790 believes 212,500 B/s against the true 1,700,000 (8x low, on the dashcam path too) | (new) |
```

`research/EXPERIMENTS.md` (verdict / status fields):

```
verdict: the absent question-time frame delta (D150 SYNC (2)) does not affect any committed main
result. 0 of 1,007,182 cloud-served units at the 1x uniform-link main operating point (115 cells,
29 arm names, seeds 4-7) reference a frame that had not finished uploading by request submission;
worst margin -2.364 ms. REAL zero, not an absent instrument (the same test returns 480 and
1,388,958 positives in the other two ask registers). 480 units are late against the cloud-ask
register, all robot recall, all landing before submission, 198 of them inside deadline and
carrying history FRESHER than at the ask by a p50 of 0.051 s, which is the opposite sign to an
absent delta. Dashcam completion times OBSERVED (outcomes.jsonl t_frame_arrive); robot and
single-shot CONSTRUCTED from the committed arithmetic and validated against the artefact's own
queue_max and busy_s. Separately: the robot link hard-code at arms_policy.py:639 EQUALS the
emulated 1,700,000 B/s in 115/115 cells, but no arm in any committed main cell executes that
site (D209 (2) scoping CONFIRMED); the believed bandwidth after arms_policy.py:790 is 212,500 B/s,
8x low, and the same defect is on the dashcam path via cstate.py:628.
status: DONE. consistency_check: PASS (7 of 7; positive control 115/115 on three committed
figures plus an independently derived 13.6 Mbit/s). mechanism_verification: n/a, measurement over
committed artefacts, no causal sweep; the zero's mechanism is traced to a read site
(cstate.py:336-341 appends frame refs only on arrival).
```
