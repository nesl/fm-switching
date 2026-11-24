# StudyNET-TIER1 - does the link emulation take effect, are the 5G numbers uplink, and what would Tier 3 cost

Session N on flash, 2026-11-23, under D214 / D215 / D216. CPU only. No GPU, no model, no server.
No cells were posted to the H100.

Read sites and line numbers in this report are at the **origin tip
`0b5cd8ab165ac433031bce6fdb86c6d2cf490fb1`**, not at the local working tree, which is behind
origin by hundreds of lines in `cstate.py`, `arms_policy.py`, `fleet/trace.py` and
`fleet/emulator.py`. Every N1 number was re-measured on a clean `git archive` of that sha after
a first pass on the stale tree, and the link numbers were identical because `fleet/links.py` is
byte-identical between the two trees.

**UPDATE 2026-11-23, after this report was first pushed at `e70948e1`.** Escalation 1 is ruled:
**Tier 1 uplink values come from cited uplink sources, namely the committed StudyE1 sweep, and
never from the Irish 5G percentiles.** With it came a correction that changes how the whole
condition set reads: **13.6 Mbit/s / 44 ms is the best-performing US carrier, not a US median.**
N3 below is rewritten on the sweep's values, the corrected label is in the provenance of every
file here, and the N1 and N4 findings are unchanged. **Tier 1 still cannot be posted:** the
ruling fixes the values, N1's finding is about reachability, and the 10 to 15 h of plumbing is
still the gate.

---

## N1 - VERDICT: the link ARITHMETIC is LIVE; the PER-DEVICE link is ABSENT

Two statements, and they must not be collapsed:

1. **Bandwidth and RTT are read and they change delivered times and decisions.** They are not a
   configured field nothing reads.
2. **There is no injection point.** `link_by_device` has exactly **two** references in the whole
   of `experiments/` - the parameter declaration at `fleet/emulator.py:245` and the write at
   `:291` - and **no caller anywhere passes it**. There is no `--uplink`, `--rtt` or `--link`
   flag on any entry point. `fleet/trace.py` emits `device_register` with
   `uplink_mbps=None, rtt_ms=None` (`:496`, `:591`, `:639`), and the emulator overwrites those
   with its own `LinkSpec` at `:483-484`. So every live2 cell ever run has used the single
   process-wide default `LK.LinkSpec()` = **13.6 Mbit/s, 44 ms, uniform over the fleet**,
   manufactured on first use at `fleet/emulator.py:303-305`.

For D215 Tier 1 as written - static **per-device** links, including a mixed fleet - the
mechanism is therefore **ABSENT**: not zero, not broken, unreachable. Fleet-wide it is
**CONSTANT** at the D75 pair. This is the same shape as the `desired_tier` failure CLAUDE.md
records, inverted: there the field was written and never read; here it is read and never
written.

### Step 2 - link parameter by link parameter

| causal link | implementing quantity | read that changes a decision or a delivered time (origin sha) | value / range in this run | verdict |
|---|---|---|---|---|
| uplink rate -> uplink occupancy | `LinkSpec.uplink_mbps` | `fleet/links.py:114` `occupancy = serialise_s(nbytes, self.spec.uplink_mbps)`, which sets `self.free_at` (`:115`) and so the FIFO queueing of every later transfer | 13.6 by default; 0.9 when injected by hand | LIVE arithmetic, ABSENT configuration |
| uplink rate -> when the cloud sees a frame | same | `fleet/links.py:117` `t_arrive`, consumed at `fleet/emulator.py:388` and `:408` `self._push(tr.t_arrive, "frame_arrived", ...)`; the coordinator is handed the frame only at that instant | per-frame upload 0.0596 s at 13.6, 0.590 s uncontended / 6.341 s median at 0.9 | LIVE |
| uplink rate -> when a question reaches the cloud | same, over `QUESTION_TEXT_B = 1200` (`fleet/emulator.py:73`) | `fleet/emulator.py:417-419` | 0.0227 s at 13.6, 0.0327 s uncontended at 0.9 | LIVE but RTT-dominated |
| uplink rate -> when a history batch lands | same | `fleet/emulator.py:506-510` | 0.2388 s at 13.6, 3.298 s at 0.9 | LIVE |
| RTT -> pull and answer delivery | `LinkSpec.rtt_ms` | `fleet/emulator.py:346` `LK.pull_s(self.link(...).rtt_ms)`, `:350-352` `LK.deliver_s(..., spec.rtt_ms, spec.downlink_mbps)`, `:395` offer arrival | 44 ms throughout | LIVE arithmetic, CONSTANT value |
| emulated link -> the POLICY's believed link | `device_register.uplink_mbps` -> `NetworkState.uplink_bps` -> `Link.bandwidth_bytes_s` | written `fleet/emulator.py:483-484`, parsed `cstate.py:286`, built `cstate.py:628`, read `arms_policy.py:631` and `:788-790`, consumed `policy/coordinator.py:130-131` `dev.link.up_s(...)` into the predicted delay | 13.6 / 44 by default | LIVE, and it tracks the emulator |
| a robot's believed link | - | **none**: `cstate.py:628` builds `NetworkState` only for `dashcams()`; a robot enters the planner at `arms_policy.py:639` with a literal `13.6e6 / 8.0` and `0.044` | constant regardless of emulation | **CONSTANT, a defect for the mixed-fleet cell** |
| a question carrying the frames the cloud lacks (D150 SYNC (2)) | - | **none**: the only query-side upload is 1200 B of text | - | **ABSENT** |
| connectivity | `NetworkState.connected` | 32 non-test read sites, e.g. `baselines/constructed.py` (8), `sim/sim1d_validate.py` (7), `arms_policy.py:633-635` | hard-coded `True` at `cstate.py:628` | **ABSENT** (N4) |

One already-ruled defect sits on this same chain and is restated because N3's instrumentation
would surface it: `cstate.py:628` sets `uplink_bps = uplink_mbps * 1e6 / 8.0`, which is **bytes**
per second, and `arms_policy.py:790` then divides by 8 again into `bandwidth_bytes_s` - an 8x
under-estimate of every believed link. StudyPLACEHOLDER-TRIAGE confirmed it and D209 (2) ruled it
narrow because the reported covex-v6 ladder never enters `arms_policy.py`. It would matter the
moment a per-device link is real, so it belongs in T2.

**This is a pattern, not two unrelated bugs, and a reader should see it as one.** Three channels
in the same neighbourhood are each written and not read, or read and not written, and every one
of them is invisible to a check that looks only at whether a quantity is non-zero and varies:

| channel | shape | consequence |
|---|---|---|
| `link_by_device` (`fleet/emulator.py:245`, `:291`) | declared and defaulted, **no caller** | the link is read everywhere and set nowhere, so the fleet is uniform by construction (N1) |
| `self._caps` (`arms.py:82`) | **one occurrence repo-wide, the write** | our own arms are BLIND to GPU-KV capacity: rungs 0 to 3 cannot observe the pool at all and the final rungs inherit that (another session, since this report was first written) |
| `uplink_bps` -> `bandwidth_bytes_s` (`cstate.py:628` -> `arms_policy.py:790`) | read, but through an 8x unit error | every believed link is under-estimated 8x where the path is live |

The first two are the `desired_tier` shape CLAUDE.md records, once in each direction. **The
operational lesson for anything built on top: a flat response across a condition that moves one
of these channels is UNEXERCISED under Rule 2, not an equivalence** - and three separate
sessions have now reached that same conclusion about three different channels within the same
few files.

### The evidence, not the argument

One dry cell, seed 4, 16 devices, 180 s, mode A, `StubCoordinator`, CPU only, run twice on the
**same trace** - once at the committed uniform link and once with every device at 0.90 Mbit/s,
the D215 Tier 1 poor rate. The second condition could only be built by passing `link_by_device`
**by hand**, which is the finding.
Output: `results/orchestration/live2/network/n1_link_emulation_probe.json`.

Frame size is the committed E10a Nexar q90 median, **63,898 B** (`fleet/data_sources.py:55`,
63,897.5 B rounded).

| quantity | 13.6 Mbit/s | 0.90 Mbit/s | predicted at 0.90 |
|---|---|---|---|
| serialisation of one dashcam JPEG | 0.037587 s | 0.567982 s | 63898 x 8 / 0.9e6 = 0.567982 s |
| per-frame upload, **uncontended** (min over 2,420 frames) | 0.059587 s | **0.589982 s** | + RTT/2 = 0.589982 s |
| per-frame upload, median over 2,420 frames | 0.059587 s | 6.341031 s | - (see below) |
| per-frame upload, max | 0.059587 s | 14.211276 s | - |
| per-question upload (1,200 B), min | 0.022706 s | 0.032667 s | 1200 x 8 / 0.9e6 + 0.022 = 0.032667 s |
| per-history-batch upload, median (48 batches) | 0.238794 s | 3.298 s | - |

**The expected scale is hit exactly: 0.59 s per dashcam JPEG at 0.9 Mbit/s**, against the brief's
"about 0.6 s". The serialisation ratio is **15.1111 = 13.6 / 0.9 exactly**.

**Read the 106x headline ratio correctly.** Median per-frame upload moves 0.0596 -> 6.341 s, a
factor of 106, and that is **not** the bandwidth ratio: at 0.9 Mbit/s a 16-device fleet
**saturates** the uplink and the extra 100x is FIFO queueing, which is a real emulated effect but
a different one. The bandwidth-only check is the uncontended minimum (9.90x including the common
RTT/2, 15.111x on serialisation alone). Reporting the 106x as "the bandwidth effect" would be
exactly the artefact-spread shape CLAUDE.md check 3 warns about.

### Step 2b - the switch reaches a decision

A paired pair of **identical command lines** on the origin tree, differing only in the injected
rate, with the real `Live2Coordinator`, the real `EmulatorBridge` and arm `policy-core`
(seed 4, 16 devices, 120 s, dry, CPU only):

| rate | registered link, all 16 devices | decisions in `decision.jsonl` | loadavg 1 m |
|---|---|---|---|
| 13.6 Mbit/s | `uplink_mbps 13.6, rtt_ms 44.0` | **814** | 2.59 |
| 0.90 Mbit/s | `uplink_mbps 0.9, rtt_ms 44.0` | **95** | 2.81 |

Outputs: `n1_policy_belief_13p6.json`, `n1_policy_belief_0p9.json`. The switch arrives at the
coordinator with its declared type and value (16 of 16 devices registered at the injected rate),
and it moves the decision count by 8.6x. The link is not merely plumbed to a number; it reaches
decisions.

One instrumentation note recorded against my own first attempt: patching `fleet.links` instead
of `links` left all 16 devices at 13.6 while the patch reported success, because
`fleet/emulator.py:68` does `import links as LK` and the two module objects are distinct. The
first run was discarded. A proof that had checked only "the switch was passed" and not "the
object under test holds it" would have passed.

### Step 4 - negative control

The 13.6 Mbit/s arm **is** the control, and it is the committed condition. It reproduces the D75
note ("about 0.04 s per dashcam frame at 13.6 Mbit/s": 0.037587 s of serialisation) and the
committed frame size to the byte. With the mechanism at its default the per-frame upload is a
**constant** 0.059587 s across all 2,420 frames, and the 0.9 cell is what shows that constant is
correct rather than short-circuited: the same 2,420 frames then spread 0.590 to 14.211 s.

### Step 5 - alternative explanation

The decision-count change (814 -> 95) could be produced by (a) the slower link delaying frames
and questions so fewer opportunities become decidable within the window [the claimed mechanism],
or (b) an exception path or a cap being hit at the slower rate and suppressing decisions. (b) is
not excluded by this probe: both cells ran to completion with equal fairness digests, but no
per-decision-kind breakdown was taken. **The decision-count delta is reported as evidence that
the switch reaches a decision, not as a result about the policy.** Nothing in this report
interprets it.

### Classification

Per CLAUDE.md Rule 2, Tier 1 as defined today would be **UNEXERCISED**: the mechanism is
reachable in the arithmetic but no entry point reaches it. **No cells posted.**

---

## N2 - the 5G numbers: the percentiles are DOWNLINK. D75's caveat is REFUTED

`p10 / p50 / p90 = 0.8954 / 9.5775 / 102.898 Mbit/s` are **DOWNLINK**, read from the
`DL_bitrate` column.

- `experiments/cost/e31_network.py:84` - `bw = float(row["DL_bitrate"])`. OBSERVED.
- `experiments/cost/e31_network.py:293` - `float(bw[i]) / 1000.0  # kbps -> Mbps`, applied only
  where `State == "D"` and the value is positive. OBSERVED.
- `experiments/cost/e31b_network.py:56-58` - the three numbers hard-coded as
  `BW_P10/P50/P90_MBPS`. OBSERVED.
- `results/INDEX.md:229` already says it in words: *"Irish 5G driving DL_bitrate (kbps->Mbps):
  p10=0.9, p50=9.6, p90=102.9 Mbps"*. The caveat in D75 was never checked against the index that
  already answered it.

**SAY IT LOUDLY, as the brief asks: every Tier 1 cell defined from these numbers would be wrong
in the easy direction.** Downlink is typically several times uplink, so a "poor" cell at
0.90 Mbit/s would be far too generous as an uplink, and the median cell at 9.58 Mbit/s is within
a factor of 1.4 of the committed uniform 13.6 Mbit/s, which is itself an uplink figure from
StudyE4 / E9 / CTRL1c. A median 5G cell built this way would barely differ from the main
operating point.

**Positive control (CLAUDE.md check 7).** Before reading anything new out of the raw dataset,
the pipeline was made to reproduce the committed number on the committed recipe. It does, to
four decimal places:

| percentile | this run (`DL_bitrate`, e31 recipe) | committed (`e31b_summary.json`) | ratio |
|---|---|---|---|
| p10 | 0.8954 | 0.8954 | 1.0000 |
| p50 | 9.5775 | 9.5775 | 1.0000 |
| p90 | 102.8978 | 102.898 | 1.0000 |
| n | 23,102 | 23,102 (`INDEX.md:229`) | 1.0000 |

So the extraction below is not a second opinion from a different pipeline.

### Uplink: the column exists and does NOT carry uplink capacity

`UL_bitrate` is present in every file of this dataset. Under the identical e31 recipe its
percentiles are **p10 / p50 / p90 = 0.017 / 0.093 / 0.2337 Mbit/s** (n = 23,134; raw
8 / 89 / 230 kbit/s). OBSERVED.

**These are not uplink percentiles and must not be used as any.** Every subset of the Irish 5G
dataset - `Download`, `Netflix`, `Amazon_Prime` - is a **download** workload. `DL_bitrate` is
near capacity there because the application saturates the downlink; `UL_bitrate` is the ACK and
control traffic of a device that is not uploading anything. A 5G uplink at 93 kbit/s is not a
capacity measurement, it is an idle uplink. Proxy declared, proxy **INVALID** for the claim
(CLAUDE.md check 6).

**So: the dataset does NOT have usable uplink percentiles, and per the brief no ratio has been
substituted.** This is an escalation, not a gap I filled.

### RTT: OBSERVED, and the prior "not available" note is wrong

`PINGAVG` is **sparsely populated**, not absent: 1,986 of 24,446 binned seconds carry a value
(8.1 % coverage).

| | ms |
|---|---|
| p10 | 68.0 |
| p50 | **80.0** |
| p75 | 92.0 |
| p90 | **120.0** |
| p95 | 165.5 |
| p99 | **351.35** |
| min / max | 65.0 / 889.0 |

All OBSERVED, column `PINGAVG`, 1 Hz samples mean-binned per integer second.

Two corrections follow. `e31_network.py:400` sets `RTT_MS = 20.0` with the comment
*"[ASSUMPTION] typical 5G RTT; PINGAVG not available in this dataset"* - the column **is**
available, and the observed p50 is 4x that assumption. And the committed harness RTT is D75's
44 ms, from the StudyE4 / E9 convention, against an observed p50 of 80 ms: a factor of 1.82,
under CLAUDE.md check 1's 2x bar but worth a ruling, since it is the term that dominates a
1,200 B question upload at any bandwidth.

### The no-cell gap distribution, as a per-device replayable schedule

OBSERVED, `CellID == -1` runs over the 16 `Download/Driving` sessions, reproducing the committed
e31b figures exactly (4,105 no-cell seconds of 28,551 = **14.3778 %**, **3,829** runs - the
committed values are 4,105, 0.1437778 and 3,829):

| run length | count |
|---|---|
| 1 s | 3,556 |
| 2 s | 270 |
| 3 s | 3 |

p50 = 1 s, p95 = 2 s, max = 3 s. The schedule is written per session as a list of
`(start_s, dur_s)` offsets in binned seconds in
`results/orchestration/live2/network/n2_irish5g_uplink_rtt_driving.json` under
`replayable_schedule`, with per-session counts beside it. A device replays its assigned
session's list and wraps at that session's length. **The offsets and lengths are OBSERVED; the
assignment of a session to a device is CONSTRUCTED.** Proxy note: `CellID == -1` is a
serving-cell field, not a measured link-liveness state; this is the committed e31b proxy and is
kept for comparability, with the register marked.

---

## N3 - Tier 1 cell definitions. NOT POSTED

`results/orchestration/live2/network/n3_tier1_cell_definitions.json`.
**Nothing was posted to the H100, because N1 says the mechanism cannot act.** Posting would
produce a flat result indistinguishable from the main operating point, which under Rule 2 is
UNEXERCISED and reads as a finding when it is not.

Arms: `simplestream`, `llf`, `mooncake`, `eco-llm`, `confidence-cascade`, our final rungs 3 and
4, `device-only`. **Seeds 4 and 5 only** - never 1 to 3, never HOLDOUT. Fleet carried over from
the committed frozen recipe: 16 devices, ratio 40:40:20, 1,200 s, mode A, per-frame. Baseline
cells are H100 **filler** under D212 and policy cells run first.

### The bandwidth ruling, 2026-11-23

**Tier 1 uplink values come from CITED UPLINK SOURCES, namely the committed StudyE1 sweep
(uplink 5 / 12 / 13.6 / 25 / 88 Mbit/s, RTT 22 / 44 / 142 ms), each with its source, and NEVER
from the Irish 5G percentiles.** Recorded in `reports/study_e1_nexar_lead.md` at `75d021d3`. The
N2 finding therefore stands in full and closes: the `DL_bitrate` percentiles are out, the
`UL_bitrate` column stays out as the ACK traffic of a download workload, and no ratio is
invented. Blocker B2 is marked RULED AND CLOSED in the JSON rather than deleted, so a reader who
meets a downlink figure in an older note sees it was ruled out and not overlooked.

Each sweep value is carried with the source the sweep itself records:

| value | source as the sweep records it |
|---|---|
| 12 Mbit/s | Khan et al. 2024, Bay Area 5G median |
| 13.6 Mbit/s | best-performing US carrier's 5G median (Ookla H2 2025) - see the correction below |
| 88 Mbit/s | Oslo |
| 22 ms | the ICCCN paper, 22 ms median (same line gives a 55 to 65 ms tail) |
| 5 Mbit/s | **NO SOURCE RECORDED IN THE SWEEP** |
| 25 Mbit/s | **NO SOURCE RECORDED IN THE SWEEP** |
| 142 ms | **NO SOURCE RECORDED IN THE SWEEP** |

**Small escalation.** The sweep's own "Network values cited" block gives a citation for 13.6, 12
and 88 Mbit/s and for 22 ms, and **none** for 5 and 25 Mbit/s or for 142 ms: those are swept grid
points, not cited values. The poor cell below uses two of them, so they are marked as unsourced
rather than dressed as citations.

### THE MAIN OPERATING POINT IS THE BEST-PERFORMING US CARRIER, not a US median

Corrected label, to be used in every figure-data provenance field and README:

> uniform 13.6 Mbit/s / 44 ms uplink: best-performing US carrier's 5G median (Ookla H2 2025),
> close to the 12 Mbit/s Bay Area 5G median (Khan et al. 2024)

Per Ookla H2 2025 these are **T-Mobile's** figures: the **highest** carrier median 5G upload
(13.57 Mbit/s) and the **lowest** carrier latency (44 ms). So the committed main operating point
sits at the **optimistic end** of the range rather than at its centre, and the measurements are
unaffected - only the label was wrong.

**Consequence for this condition set, and it changes how the whole thing reads: a "median"
condition is NOT the main operating point, it is a different and slower cell.** The three cells
below are therefore positioned against the sweep's own range, not against 13.6 Mbit/s as though
it were typical. The label is now carried in the provenance of every file here, including the
control arm's: `n1_link_emulation_probe.json`, `n1_policy_belief_13p6.json` and
`n1_policy_belief_0p9.json` each carry `main_operating_point_label`, and the two belief cells and
the stub probe were re-run to put it there rather than having it patched into generated output.

### The three cells

| cell | uplink | RTT | which RTT and why |
|---|---|---|---|
| **median** | **12 Mbit/s** (Khan et al. 2024, Bay Area 5G median) | **44 ms** (CITED) | 12 is the only sweep value cited *as* a median that is not the best-carrier figure, so 13.6 is deliberately not used here. 44 ms is the sweep's middle value and keeps continuity with the main operating point. **The choice is flagged, not hidden:** the sweep's cited median RTT is 22 ms, which is 3.6x below this study's OBSERVED PINGAVG p50 of 80 ms, so a "median" RTT could defensibly be 22 (cited), 44 (continuity) or 80 (observed). |
| **poor** | **5 Mbit/s** (unsourced in the sweep) | **142 ms** (unsourced in the sweep) | 142 ms is the sweep's tail and the poor cell is the tail condition. D215 asks for p99 beside it: the OBSERVED p90 is 120 ms and p99 is 351 ms, so 142 ms sits between the observed p90 and p99. |
| **mixed fleet** | **slow 5 / median 12 / fast 88 Mbit/s** | **142 / 44 / 22 ms** | each class takes the sweep RTT at its end of the range. **Pairing a rate with an RTT is CONSTRUCTED:** the sweep is a full 5x3 grid and records no joint distribution, and the Irish dataset gives no measured uplink bandwidth-RTT pairing either. 13.6 and 25 Mbit/s are the two sweep values not used, and the JSON says why: 13.6 would make a third of the mixed fleet identical to the uniform condition, and 25 carries no source while the fast class already has the cited 88. |

My OBSERVED RTT work is kept and stated beside the cited values on every cell, with the register
on each: **PINGAVG p50 / p90 / p99 = 80 / 120 / 351 ms, OBSERVED** from the Irish 5G
Download/Driving trace (n = 1,986 populated binned seconds, 8.1 % coverage), against the sweep's
**22 / 44 / 142 ms, CITED**. The applied value in each cell is the cited one, per the ruling; the
observed one is reported beside it so the gap is visible rather than resolved silently.

**Expected scale for the poor cell, so a real effect is distinguishable from a plausible-looking
one:** at 5 Mbit/s one 63,898 B dashcam JPEG serialises in 0.1022 s and arrives 0.1733 s after
capture on an idle uplink at 142 ms RTT. **Saturation at 5 Mbit/s must be measured, not
assumed** - the N1 probe showed that at 0.9 Mbit/s the same frame takes 0.568 s uncontended while
16 devices push the median to 6.34 s, so the queueing term, not the serialisation term, is what
decides whether a poor cell is a different regime.

### A defect in my own fairness property, found and fixed

The mixed-fleet assignment is the one thing in this section whose whole purpose is to be
identical across arms, and the first version was not. It seeded
`random.Random(("tier1-mixed-5g", seed))`, and `random.seed` falls back to `hash()` for an
arbitrary object, so a tuple containing a string is seeded from a **PYTHONHASHSEED-randomised**
hash. Two successive invocations in this session produced **different** assignments for seed 4,
and since two arms run in two processes that silently destroys the only property the function
exists to provide. It would have passed any check applied to one process.

Fixed by seeding with a string (`"tier1-mixed-5g|%d"`), which `random` hashes with sha512 itself.
**Proof, now part of the output:** the assignment is recomputed in fresh subprocesses under
`PYTHONHASHSEED` 0, 1 and 12345 and must be identical - `identical: true` for both seeds - and it
is also identical across three separate invocations of the generator. The class labels were
renamed `slow / median / fast`, because `p10 / p50 / p90` named the ruled-out downlink source.

Class split 6 / 5 / 5 at 16 devices; both seeds' full per-device tables are in the JSON.

D215 / F12 instrumentation each cell must collect: applied per-device link parameters logged per
cell **read back from the object the emulator holds, not from the CLI arguments**; per-frame
bytes with the full `UplinkTransfer` record (`t_offer`, `t_start`, `queue_s`, `t_arrive`) per
device; per-device uplink queueing (`n`, `busy_s`, `queue_p50/p99/max`); per-query bytes and
upload time; history-batch bytes and upload time; the standard F1 / F2 / F3 / F13 fields; and -
new, from N1 - **the policy's believed link beside the applied one**, because the two are wired
separately and a robot's belief is currently a hard-coded constant.

### What building Tier 1 takes

| | work | h |
|---|---|---|
| T1 | a `--link-plan` JSON on the cell drivers and `run_live2_real.py`, built into `link_by_device`, carried across the `procsplit` two-process wire, and logged into `run_meta` | 3 to 5 |
| T2 | `cstate` carries a per-device link for **every** type, not only dashcams (`cstate.py:628`), `arms_policy.py:639` stops hard-coding a robot's 13.6 Mbit/s, and the 8x double-division below is fixed | 2 to 3 |
| T3 | the F12 instrumentation above, plus the scorer fields | 2 to 3 |
| T4 | tests, plus a byte-identity proof that the default plan reproduces the committed digests exactly, plus Step 2b on one cell | 3 to 4 |
| | **total, Tier 1 only** | **10 to 15** |

No new record kind is needed, so the D96 (2) fairness digest is untouched - which is why Tier 1
is cheap and Tier 3 is not.

---

## N4 - Tier 3 minimal outage estimate. NO BUILD. `cstate.py` was read, not touched

D191 (3) recorded "emulation absent (`cstate.py:595` hard-codes `connected=True`; build 30 to
47 h plus three rulings)". Confirmed, at the origin tip the line is **`cstate.py:628`**, and the
flag has **32 non-test read sites** (`baselines/constructed.py` 8, `sim/sim1d_validate.py` 7,
`arms_policy.py` 3, one each in fourteen baseline adapters and `arms_published.py`), consistent
with D191's "about twenty".

Two facts that move the estimate in opposite directions, both newly checked:

- **Cheaper than it looks on the policy side.** `policy/coordinator.py:791-810` already
  implements `on_outage` (pause this device's pending items, discount the state value by
  `P(reachable within H_s)`) and `on_reconnect` (return the backlog). Spec 7.5 is built.
- **More expensive than it looks on the wiring side.** `on_reconnect` has **no production
  caller** - only tests - so there is no transition back. And `on_outage` is called from
  `arms_policy.py:635` on **every** sync while disconnected, with `p_reconnect` hard-coded
  `0.0`; it needs edge-triggering or it will re-pause and emit a decision every period.

### Harness work (independent of the counterfactual)

| | work | h |
|---|---|---|
| H1 | an outage schedule per device on the drivers and across the `procsplit` wire (shares T1's plumbing) | 2 to 3 |
| H2 | emulator outage state and `outage_start` / `outage_end` heap events; gate `_upload`, the pull, the offer and the answer delivery so nothing crosses a down link | 4 to 6 |
| H3 | device-side buffering and reconnect drain, with the type-aware rule for our arms (stale dashcam frames **dropped**; robot history oldest-first per D150, or question-first) and **FIFO for baselines**, draining through the existing `UplinkQueue` so the recovery burst pays real serialisation | 5 to 7 |
| H4 | connectivity visible to the coordinator: a per-device `connected` for every type, and a `device_disconnect` / `device_reconnect` record kind | 2 to 3 |
| H5 | **the D96 (2) consequence of H4**: `TRACE_KINDS` and `WIRE_KINDS` are closed sets and the fairness digest covers the presented stream, so a new kind changes every digest. Either the digest definition is versioned and a two-tree identity proof is run at one sha, or the outage is generated inside the emulator and never enters the trace. Whichever is chosen, it is a proof, not an edit | 4 to 6 |
| H6 | `arms_policy` edge-triggering, a real `p_reconnect`, and the first production call of `on_reconnect` | 1 to 2 |
| H7 | instrumentation: outage start and end, backlog bytes and items at reconnect, recovery time to the first on-time cloud answer, post-reconnect windows, harm to other devices, backlog size over time | 3 to 5 |
| H8 | schedules: the realistic replay (N2's per-session 1 to 3 s gap lists, already extracted) and the 30 s stress, one device and correlated | 1 to 2 |
| H9 | tests; default-off byte identity for every arm; Step 2b decision diff; the Step 4 negative control (zero-length outages must collapse every arm to its committed cell) | 4 to 6 |
| | **harness total** | **26 to 40** |

### What the counterfactual's sync leg adds, costed separately

| | work | h |
|---|---|---|
| C1 | sync ordering as a counterfactual decision: whose backlog to prefill, and for a question arriving before catch-up, question-first against wait against leave-to-device, valued in D191 (2) deviation units (weighted counts of expected on-time cloud answers, margin `w_d x 0.6582`) | 6 to 10 |
| C2 | its Step 2b against naive recovery (FIFO backlog, `deficit_gain` 0), which is the decisive comparison D215 names, plus the unit proofs and the characteristic-decision count being non-zero | 3 to 5 |
| | **counterfactual sync leg** | **9 to 15** |

**Total 35 to 55 h**, against the prior estimate's 30 to 47 h. **I agree with its shape and I am
higher at both ends, for two reasons the prior estimate appears not to price.** First, H5: adding
a record kind is not a code change, it is a change to the object every committed trace and every
fairness digest is keyed on, and this project has already had one false alarm from comparing
digests across recipes. Second, H3 is not a buffer but a policy-bearing component - the
type-aware backlog rule is part of the contribution, so it needs its own proof that the
characteristic decision (dropping a stale dashcam frame; choosing question-first) occurs at least
once, per CLAUDE.md's port rule.

And one dependency the prior estimate does not mention: **D215's "question-first" backlog rule is
not expressible today.** A question carries 1,200 B of text and nothing else
(`fleet/emulator.py:73`, `:417`); D150 SYNC (2)'s on-demand delta does not exist. Either that is
built (4 to 8 h, inside H3's blast radius) or the rule is redefined to mean ordering the
device's buffered history so the question's evidence drains first. Without one of the two, a
"question-first against oldest-first" comparison would be ABSENT in the Step 2 sense.

### Rulings needed (I count four, not three)

1. **The uplink bandwidth.** The percentiles are downlink. Reuse them as a symmetric-link
   assumption, find an uplink-capacity source, or keep 13.6 Mbit/s and sweep a scaling factor.
   Blocks Tier 1 and Tier 3 alike.
2. **Does a question carry a frame delta?** Without it "question-first" has no channel.
3. **Outage in the trace or in the emulator?** The first changes every fairness digest; the
   second keeps the schedule out of the trace artefact. One of the two.
4. **Is the baselines' FIFO reconnect implemented once in the shared harness** (which makes it
   fair by construction and is what D215's "baselines upload FIFO" implies) **or per arm?**

### Not mine

`cstate.py` was **read only**, as instructed; nothing in it was edited, and no estimate above
assumes an edit I would make.

---

## Results consistency check

1. **Cross-check against committed measurements.**

| quantity | this run | prior committed | source of prior | ratio | agree |
|---|---|---|---|---|---|
| Irish 5G DL p10 / p50 / p90 (Mbit/s) | 0.8954 / 9.5775 / 102.8978 | 0.8954 / 9.5775 / 102.898 | `e31b_summary.json`, `INDEX.md:229` | 1.0000 | agree |
| D-state rows behind those percentiles | 23,102 | 23,102 | `INDEX.md:229` | 1.0000 | agree |
| no-cell seconds / fraction / runs | 4,105 / 0.143778 / 3,829 | 4,105 / 0.1437778 / 3,829 | `e31b_summary.json` | 1.0000 | agree |
| dashcam frame bytes | 63,898 | 63,897.5 | `fleet/data_sources.py:55` (StudyE10a) | 1.0000 | agree |
| dashcam frame serialisation at 13.6 Mbit/s | 0.037587 s | "about 0.04 s" | D75 note | 1.06 | agree |
| harness RTT | 44 ms (applied) vs 80 ms (observed p50) | 44 ms | D75 | 1.82 | **flagged, under 2x, different sources: D75 is the StudyE4 / E9 convention, 80 ms is this dataset's PINGAVG** |
| assumed RTT in E31 Part D | 80 ms observed | 20 ms assumed | `e31_network.py:400` | 4.0 | **DISAGREE and explained: the comment says PINGAVG is unavailable; it is 8.1 % populated** |
| sweep's cited median RTT | 80 ms observed (PINGAVG p50) | 22 ms cited | `study_e1_nexar_lead.md`, "Network values cited" (ICCCN paper) | 3.6 | **DISAGREE, over the 2x bar. Explained by setting rather than reconciled: 22 ms is a paper's figure, 80 ms is a driving trace in Ireland. Both registers carried; every cell says which it applies.** |
| per-frame upload at 13.6 / per-question / decision counts, re-run at loadavg 0.2 after the first pass at 2.6 | 0.059587 s / 0.022706 s / 814 and 95 | 0.059587 s / 0.022706 s / 814 and 95 | this session's own first pass | 1.0000 | agree, and incidentally shows the dry non-realtime cell is load-independent |

2. **Physical plausibility.** 63,898 B in 0.567982 s implies 112,500 B/s = 0.900 Mbit/s exactly,
and in 0.037587 s implies 1.70 MB/s = 13.6 Mbit/s exactly. No rate in this report is faster than
the rate it was configured at, and nothing here touches a prefill or decode curve. The `0.9`
cell's median is **slower** than its own serialisation, not faster, which is the direction
queueing can go.

3. **Distribution sanity.** Per-frame upload at 13.6 Mbit/s is a **constant** 0.059587 s across
all 2,420 frames, to six decimals - exactly the shape that normally advertises breakage. It is
reported with its spread and with the reason: every monitor frame carries the identical default
byte count (no Part-2 manifest in this cell) and the uplink never queues at 13.6 Mbit/s. The
0.9 Mbit/s cell is the evidence that the constant is correct and not short-circuited, since the
same frames there spread 0.589982 to 14.211276 s. The **artefact-spread** hazard is flagged in
N1: the 106x median ratio is saturation, not bandwidth. Per-session minima, medians and maxima
are given for every bandwidth and RTT figure in the N2 JSON rather than a bare median.

4. **Definition audit.** `upload time` = `bytes x 8 / uplink + RTT / 2`, of which only
`bytes x 8 / uplink` occupies the uplink (`fleet/links.py:45-54`); unchanged from D75.
`per-frame upload` here = `t_frame_arrive - t_opportunity` from `outcomes.jsonl`, which is the
delivered time the scorer reads, cross-checked against the raw `UplinkTransfer` log and equal.
`dashcam frame` = 63,898 B (E10a Nexar q90 median); `history frame` = 24,570 B (E10a Sember q88
D2); `question` = 1,200 B. `binned second` = mean of the 1 Hz samples inside an integer second,
NaN if empty - identical to `e31_network.py:100-110`, and the identity is demonstrated by
reproducing its percentiles and its gap counts, not asserted. `no-cell gap` = a run of
`CellID == -1` over binned seconds. `mixed fleet` = a seeded function of (seed, roster) only.
No name is used here with two definitions. **One name was corrected:** the committed
13.6 Mbit/s / 44 ms condition was labelled an "Ookla H2 2025 US 5G median" and is the
**best-performing US carrier's** figures (highest carrier median upload, lowest carrier
latency); the corrected label is now in the provenance of every file here. **And one of my own
labels was wrong:** the mixed-fleet classes were named `p10 / p50 / p90` after the ruled-out
downlink percentiles and are now `slow / median / fast`.

5. **Claim linkage.** N1 bears on **D150 (4)** ("links are emulated in the harness per device
(bandwidth, RTT, outages; identical across arms)") and **weakens** it: the emulation is live but
uniform-only and per-device is unreachable. It bears on **D215**'s instruction to "first verify
the per-device link emulation actually takes effect" and answers it in the negative. It bears on
**D30** (delivered delay everywhere; per-device link estimate) and supports the delivered-delay
half while weakening the per-device half. N2 bears on **D75**'s explicit unconfirmed caveat and
**refutes** it; the user's 2026-11-23 ruling closes it by sourcing Tier 1 uplinks from the
committed StudyE1 sweep instead, and the accompanying correction re-labels the main operating
point as the best-performing US carrier rather than a US median, which **weakens** any reading of
the committed results as holding at a typical 5G uplink. N4 bears on **D215 Tier 3** and **D191 (3)**. Nothing here is scoped out by
FORMULATION.md: no KV moves between tiers anywhere in this report, and no payload is a KV cache.

6. **Proxy validity.** Three proxies declared. (a) `UL_bitrate` as an uplink capacity -
**INVALID**, the subset is a download workload, so it may not be used for any headline or any
cell; stated and not used. (b) the downlink percentiles as an uplink - **INVALID**, which is the
N2 finding. (c) `CellID == -1` as a radio gap - the committed e31b proxy, a serving-cell field
rather than a measured link state; kept for comparability with the register marked, and used only
to describe a schedule, not to support a conclusion.

7. **Validate the control, not only the result.** The N2 **positive control** reproduces the
committed DL percentiles and the committed gap counts exactly before anything new is read out of
the dataset, so a failure there would have meant a broken pipeline rather than a wrong committed
value. The N1 **control arm is the committed condition itself** (13.6 Mbit/s, 44 ms) and it was
cross-checked against D75's own note and the committed E10a frame size before the 0.9 cell was
read. Two impossible successes were caught this way and both are recorded above against
the author's own work: the first belief-probe pass patched the wrong module object and reported a
0.9 Mbit/s run in which all 16 devices were registered at 13.6 Mbit/s; and the first mixed-fleet
assignment was seeded from a randomised `hash()` and silently differed between processes, which
is the one property that definition exists to guarantee. Both now have a positive check that
fails if they regress: the registered-link readback, and a three-`PYTHONHASHSEED` subprocess
proof in the generator's own output.

## Mechanism verification status

Steps 0, 1, 2, 2b, 3 (the per-frame and per-question traces above, with the arithmetic checkable
by hand), 4 and 5 are recorded, and the outcome is a **stopping condition**: Step 2 returns
ABSENT for the per-device link and for the query delta, and CONSTANT for a robot's believed link.
**Per the rules, no sweep was run and no cells were posted.** This report makes no claim about
any policy.

## Provenance and load

All work CPU-only on flash, `conda run -n fmtk python`. Read sites at origin
`0b5cd8ab165ac433031bce6fdb86c6d2cf490fb1`. Every cell here is **DIAGNOSTIC**, never a proof bar
and never a Step 2b baseline for another session's comparison, so the D216 (1) alone rule is not
invoked; loadavg is recorded as a magnitude per cell anyway (1 m load 2.26 to 2.81 throughout,
with another session's `d210_kv025_one_cell.py` and `cf_pd_one_cell.py` running). The paired
belief cells are identical command lines differing in one argument, which is a legitimate
before/after method and not a duplicate run.

All three N1 cells were **re-run** after the 2026-11-23 label correction so the corrected
main-operating-point label is in their generated provenance rather than patched into generated
output. The re-run happened on a near-idle box (1 m load **0.20 to 0.27** against 2.26 to 2.81
for the first pass) and reproduced every figure exactly, including the 814 and 95 decision
counts, which is the expected behaviour of a non-realtime dry cell and a small free check that
nothing here depends on machine load.

The condition this report calls the **main operating point** is, in the corrected label,
"uniform 13.6 Mbit/s / 44 ms uplink: best-performing US carrier's 5G median (Ookla H2 2025),
close to the 12 Mbit/s Bay Area 5G median (Khan et al. 2024)". The **0.90 Mbit/s** rate used
throughout N1 is a **probe rate only**, chosen so the injected change is large and checkable by
hand; it is not a Tier 1 cell value and, after the ruling, no Tier 1 value comes from the Irish
5G percentiles at all.

## Outputs

| file | what |
|---|---|
| `results/orchestration/live2/network/n1_link_emulation_probe.json` | the two-rate stub cell: applied link params, per-frame / per-question / per-batch upload spreads, uplink queueing, and the plumbing greps |
| `results/orchestration/live2/network/n1_policy_belief_13p6.json` | paired real-coordinator dry cell at the committed rate |
| `results/orchestration/live2/network/n1_policy_belief_0p9.json` | the same at 0.90 Mbit/s |
| `results/orchestration/live2/network/n2_irish5g_uplink_rtt_driving.json` | DL positive control, UL percentiles with their validity, RTT percentiles, and the per-session replayable gap schedule |
| `results/orchestration/live2/network/n3_tier1_cell_definitions.json` | the three Tier 1 cells on the StudyE1 sweep values with a source per value, the seeded mixed-fleet assignment for seeds 4 and 5 with its three-`PYTHONHASHSEED` reproducibility proof, the cited-against-observed RTT registers, the F12 instrumentation and the blockers (B2 ruled and closed) |
| `experiments/orchestration/live2/n1_link_emulation_probe.py` | the N1 probe |
| `experiments/orchestration/live2/n3_tier1_cell_definitions.py` | the N3 definitions generator |
| `experiments/cost/n2_irish5g_uplink_rtt.py` | the N2 extraction |
