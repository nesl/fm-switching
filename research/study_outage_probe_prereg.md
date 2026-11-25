# StudyOUTAGE-PROBE pre-registration: does an idle robot history survive an outage?

**Status: PRE-REGISTRATION ONLY. Nothing is built. No `experiments/` push until overnight block A finishes
(D238).** Written before any probe code exists, so that the expectations below cannot be fitted to a
result. Recorded by flash's main session, 2026-11-24, pinned to one `origin/main` sha.

## The question

**Under rung 3's real traffic mix at kv0.5r, does a robot history that receives no requests survive 120 s
and 300 s in the GPU and host tiers, and do periodic touches keep it alive?**

## Why it cannot be answered from committed cells

**Rung 3 has only 8 natural idle gaps over 60 s across kv0.5r s4 to s7, so 120 s and 300 s are
UNOBSERVED.** The planner's CPU-side figures, which this probe exists to test rather than to assume:
rung-3 kv0.5r writes **260 to 400 tokens/s** to the 27 GiB host tier (**110,592 tokens**, a figure that
appears in 43 committed result files), so the tier cycles every **280 to 430 s**; `llf` writes
**4,500 tokens/s** and cycles every **25 s**. Natural gaps of 30 to 60 s leave rung-3 robot histories cold
**0.5 to 2 percent** of the time and llf's **100 percent**. **All of these are planner estimates, not
engine measurements, and the probe's purpose is to measure them.**

## Design

1. **One robot history of about 15k tokens**, built from a real robot session's frames.
   **PRE-REGISTERED INPUT TO VERIFY, NOT ASSUME: that 15k is the median robot history size at question
   time.** It is taken from the planner and must be confirmed against the committed cells before the probe
   runs; if the measured median differs, the probe uses the measured value and the change is recorded.
2. **Pressure: replay the request stream of every OTHER device** from the committed cell
   `results/orchestration/live2/frozen_test/runs/covex-v6-fair-final_n16_s4_1200s_h27_3t_kv0.5r_L3_epg_rq30`
   (17 files present, `request.jsonl.gz` among them), keeping **original timing and per-request offload
   controls** (the per-type retention rule), over a window starting **mid-run, in steady state**.
3. **Silence the probe robot for T = 60, 120 and 300 s**, then send its next request (history plus one
   frame) and classify as **GPU-warm, HOST-warm or COLD** from cached and external tokens, via the
   harness's own `classify_residency(local, external, prompt_tokens)`.
4. **Arms:** (a) **no touches**; (b) **a touch of the probe history every 60 s while silent**;
   (c) **llf's offload controls, all types retained, as a POSITIVE CONTROL FOR EVICTION.**
5. **Twins: every point runs twice**, or against a twin history as in StudyENG1c. Engine flags as the
   kv0.5r cells: `--max-model-len 31472` and `--num-gpu-blocks-override 1968`, **with the last flag in
   argv winning, which must be asserted rather than assumed.**

## Pre-registered expectations, recorded before the build

**Written so that each outcome means something in advance.** The planner's model predicts the host tier
cycles every 280 to 430 s, so:
- **T = 60 and T = 120 should be HOST-warm or better under arm (a)**, because both are well inside one host
  cycle. **A COLD at T = 120 under arm (a) would refute the planner's host-cycle estimate**, which is the
  single most useful thing this probe can return.
- **T = 300 under arm (a) straddles the predicted cycle (280 to 430 s), so it is genuinely uncertain and no
  outcome refutes anything.** This is the point the probe exists to measure rather than to predict.
- **Arm (b) should hold GPU-warm or HOST-warm at every T**, since a 60 s touch interval is shorter than
  every predicted cycle. **If arm (b) goes COLD, touches do not keep a history alive**, which would bear
  directly on D236: touches are currently kept in the freeze candidate provisionally, and a touch that
  does not preserve residency under pressure is evidence they are not doing the job they are kept for.
- **Arm (c) must go COLD at T = 60**, per the 25 s turnover. **This is a SANITY CHECK, not a result.**

## Sanity checks, which gate the result rather than following it

- **T = 0 must classify GPU-warm.** If it does not, the probe is broken, not the engine.
- **Arm (c) at T = 60 must classify COLD.** If it does not, the pressure is not reaching the engine and no
  arm (a) or (b) survival reading means anything. **This is the positive control, and the registered rule
  is that a failure here voids the whole run rather than being reported as an arm result.**
- **Host write rate during the probe is compared with the source cell's**, as a fidelity check on the
  replay. **The replay is OPEN-LOOP: the other devices' requests come from a cell in which the probe robot
  WAS active, so the engine state cannot match the source exactly.** The write-rate comparison is what
  bounds that infidelity, and a large divergence makes the survival readings descriptive of the probe
  rather than of rung 3.
- **Disk guard: refuse below 15 GB. GPU 2 exclusive. An INVALID point is excluded, not zeroed.**

## Estimate, reported before building

| item | hours |
|---|---|
| Replay pressure from the cell's `request.jsonl.gz`, original timing, per-request offload controls | **4 to 6** |
| **Add `--num-gpu-blocks-override` to the harness: it has ZERO hits there today** | **1 to 2** |
| Silence window and the three T values, wired to the existing classifier | 2 to 3 |
| Arms (a), (b), (c), including inverting the per-type retention rule for (c) | 2 to 3 |
| Twins | 0.5 |
| Sanity checks and the host write-rate fidelity comparison | 2 to 3 |
| Proofs, provenance, report | 2 to 3 |
| **TOTAL BUILD** | **14 to 20 h** |

**What the harness already supplies, so these hours are additive rather than from scratch:**
`experiments/orchestration/live2/confirm_engine_actions_32b.py` (1,680 lines) carries
`classify_residency` at :231, `Engine` at :247, `History` at :456, `Filler` at :529, `preflight` at :608,
three `measure_m*` stages and a `selftest` at :1247, with 48 references to `cached_tokens`, 34 to
`external`, 40 to touches, 17 to twins and 13 to offload. **The missing pieces are the block override and
the real-cell replay; everything else is wiring.**

**GPU time: 90 to 150 minutes.** 3 values of T by 3 arms by 2 twins is **18 points**, plus T = 0 sanity
points. Each point needs a steady-state lead-in of about 60 s plus T seconds of replay, so one arm's three
T values cost about 11 minutes of pressure, 66 minutes across three arms and two twins, plus engine start
and stop (about 60 to 90 s each) and the sanity points.

*** SCHEDULING WARNING: THIS IS NOT A CELL-LENGTH SLOT. *** A normal cell is about 22 minutes; this probe
needs **a contiguous exclusive block of 2 to 2.5 hours**, which displaces roughly six cells. **And "after
block A" needs a ruling, because D238 puts `ptg` directly after block A and then blocks B, C and D run to
about 06:56.** The options are: immediately after `ptg` (displacing part of block B), or after block D. **A
2 to 2.5 h exclusive block is a scheduling decision for the user, not something to slot in silently.**

## What this probe cannot establish

- **Anything about policy behaviour.** It is an engine-level residency probe. It measures whether a history
  survives, not whether any arm's decisions are good.
- **The natural-gap statistics it is motivated by.** Those come from the planner, CPU-side and unverified,
  and the probe does not validate them; it measures survival at three chosen T values instead.
- **Closed-loop behaviour.** The replay is open-loop by construction, bounded only by the write-rate
  fidelity check.
- **Anything at 1x.** The probe is specified at kv0.5r only.
- **A floor.** Twins give a repeatability reading at each point, not a noise floor over conditions.
