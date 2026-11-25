# StudyOUTAGE-PROBE pre-registration at 1x memory (SUPERSEDES the kv0.5r version at `a5515060`)

**Status: PRE-REGISTRATION. NOTHING IS BUILT. *** AND THE BUDGET RULE HAS FIRED: THE DESIGN AS SPECIFIED
COSTS ABOUT 157 GPU MINUTES, WHICH EXCEEDS THE 90-MINUTE STOP THRESHOLD, SO I AM STOPPING AND REPORTING
RATHER THAN BUILDING. *** Options that fit the budget are set out below for the user to rule on.

**Supersession.** `research/study_outage_probe_prereg.md` (`a5515060`) specified this probe at `kv0.5r`.
**Per D240 that is wrong: memory and network are never stacked, and all outage work runs at 1x only.**
This note replaces it on that point. The earlier file is left in place as the record of what was
superseded rather than edited.

## The question, unchanged except for the pool

**At 1x memory, under rung 3's real traffic mix, does a robot history with no requests survive 60, 120 and
300 s of silence in the GPU and host tiers? Do periodic touches keep it alive?**

## Engine configuration, confirmed against the committed 1x cell rather than assumed

Read from `covex-v6-fair-final_n16_s4_1200s_h27_3t_L3_epg_rq30/header.json`:
`gpu_kv_tokens` **62,944**, `server_extra_flags` **None**, `robot_deadline_s` **3.0**. So the probe runs
`--max-model-len 32768` with the native 27 GiB host offload and **NO `--num-gpu-blocks-override`**, because
the 1x cells pass no extra server flags. **This removes the 1 to 2 h harness item the kv0.5r version
needed, since `confirm_engine_actions_32b.py` has zero references to the block override.**
**The last occurrence of a flag in argv wins, and that must be ASSERTED in the preflight rather than
assumed.**

## *** THE FINDING THAT DRIVES THE COST, AND IT IS A CORRECTION TO MY OWN EARLIER ESTIMATE ***

The earlier note assumed a **60 s** steady-state lead-in. **That is wrong, and not by a little.** The host
tier holds **110,592 tokens** and rung 3 writes **260 to 400 tokens/s**, so **filling it takes 276 to 425
seconds, about 316 s at the midpoint.**

*** AND THE LEAD-IN IS NOT OPTIONAL, WHICH IS THE WHOLE POINT: WITH A HOST TIER THAT IS NOT FULL, NOTHING
CAN BE EVICTED FROM HOST, SO EVERY ARM RETURNS HOST-WARM AND THE MECHANISM UNDER TEST IS UNREACHABLE. ***
That is an **ABSENT LINK** by CLAUDE.md Step 2, not a cheaper experiment. A probe run with a 60 s lead-in
would return a clean-looking table of HOST-warm survivals that measured only an empty tier. **This is
exactly the failure mode the mechanism-verification protocol exists to catch, and it was caught in the
estimate rather than in the data.**

**A second-order problem follows from it.** The 276 to 425 s figure is derived from the **kv0.5r** write
rate. **The 1x host write rate has NOT been measured cleanly**, which is one of the questions this study is
meant to answer, so the lead-in is itself uncertain until it is measured.

## Cost, three designs

| design | GPU minutes | problem |
|---|---|---|
| **(i) SEQUENTIAL as specified**: 18 points, each with its own 316 s lead-in | **about 157** | **over the 90-minute stop threshold** |
| **(ii) NESTED**: 3 twin histories silenced together per run, probed at 60, 120 and 300 s | **about 74** | **3 probe histories at 15k are 45,000 tokens, which is 71 percent of the 62,944-token 1x GPU pool**, so the probe would distort the pressure it is trying to measure. Two histories is 48 percent. |
| **(iii) PRELIMINARY ONLY**: one arm, one rep, measure the 1x host write rate and nothing else | **about 8** | answers one real question and firms the lead-in, but is not the probe |

Build hours, at 1x: **12 to 18 h** (the kv0.5r estimate minus the block-override item). What the harness
already supplies is unchanged: `classify_residency` at :231, `Engine` at :247, `History` at :456, `Filler`
at :529, `preflight` at :608, three `measure_m*` stages and a `selftest`, with 48 references to
`cached_tokens`, 34 to `external`, 40 to touches and 17 to twins. **The genuinely new work is the real-cell
pressure replay.**

## *** RECOMMENDATION, FOR THE USER TO RULE ***

**Spend the 8 GPU minutes on design (iii) first.** It measures the 1x host write rate, which is a question
the study is chartered to answer in its own right, and it **replaces the derived 276-to-425 s lead-in with
a measured one**, which is what sets the cost of everything else. **Re-estimate after it.** If the 1x write
rate is materially higher than kv0.5r's, the lead-in shortens and design (i) may come under the threshold
on its own; if it is lower, the probe is more expensive than either figure above and that is worth knowing
before 14 hours of build.

**I am not building either (i) or (ii) tonight.** (i) breaches the stated rule. (ii) is within budget but
buys it by holding most of the 1x pool in probe histories, and a probe that distorts the pressure it
measures is the kind of result that passes every arithmetic check and means nothing.

## Pre-registered expectations, recorded before any build

- **T = 60 and T = 120 should be HOST-warm or better under arm (a)**, both inside one host cycle. **A COLD
  at T = 120 would refute the planner's host-cycle estimate**, the single most useful thing the probe can
  return.
- **T = 300 straddles the predicted cycle, so no outcome there refutes anything.** That is why it is being
  measured rather than predicted.
- **Arm (b) should hold at every T.** **If it goes COLD, touches do not keep a history alive under
  pressure**, which bears directly on D236, where touches are kept in the freeze candidate provisionally.
- **Arm (c) must go COLD at T = 60.** This is a **sanity check, not a result**, and its failure voids the
  run rather than being reported as an arm outcome.

## Sanity checks and gates

**T = 0 must classify GPU-warm**, or the probe is broken rather than the engine. **Arm (c) at T = 60 must
classify COLD**, or the pressure is not reaching the engine and no survival reading means anything.
**The probe's host write rate is reported against the source cell's**, as the fidelity check on an
**open-loop** replay: the other devices' requests come from a cell in which the probe robot WAS active, so
engine state cannot match the source exactly, and that comparison is what bounds the infidelity.
**Disk refusal below 15 GB. GPU 2 exclusive. An INVALID point is excluded, not zeroed.**

## What this probe cannot establish

- **Anything about policy behaviour.** It is an engine residency probe.
- **The natural-gap statistics that motivate it**, which are planner-side and unverified.
- **Closed-loop behaviour**, by construction.
- **Anything at reduced memory.** Per D240 the probe is 1x only, and the kv0.5r figures quoted above are
  inputs to the estimate, not results that transfer.
- **A noise floor.** Two repetitions give repeatability at a point, not a floor over conditions.
