# SCOPING: LIVE LINK STATE AND POLICY-CONTROLLED POST-OUTAGE SYNC (2026-11-26T00:03Z). ESTIMATE ONLY, NOTHING BUILT. About 55 h, so it exceeds the 12 h escalation limit.

Read at origin d06f9c7d. Supersedes D273 "frames lost". Needs rulings on the design choices below before any build.

## Four findings that change the scope
1. **Robots are not in `obs.streams`.** `cstate.py:660` builds streams from `self.dashcams()` only (`:457`, type == dashcam), and `NetworkState(connected=True)` is at `:677`. Every baseline read of `s.network.connected` iterates dashcams, so with a robot-only outage a live `connected` changes NO baseline. **This corrects an earlier flag of mine that said baselines would change.** A robot link signal needs a NEW per-device Observation field read by no existing arm.
2. **`plan_sync` exists** (`v5/cf_planner.py:799`, QUESTION_FIRST / WAIT / LEAVE_TO_DEVICE) but its only caller is the internal dispatch at `:461`; it is wired into no arm. It still takes accuracy arguments; whether it is in the D177 on-time currency needs a read.
3. **No coordinator-controlled upload hook exists.** `emulator.py:_plan` pushes every history batch at its time and `:519-525` uploads at once (FIFO per device, `links.py:112-120`). The coordinator can only send `pull_request` and `cloud_answer`. Gated sync needs a held-backlog state, a `sync_offer` event, a new `sync_pull` reply, and a correction of the cloud's `cum_tokens` belief (held = cum minus unreleased, plus the 31-token D2 header re-attribution found in D273).
4. **The NESTOUT build is not on origin.** It lives only in the handoff change set (trace.py 1,455 lines against 1,216 on origin). It must be merged first.

## Hours (flash CPU, build plus proofs, no cells)
| part | h | | part | h |
|---|---|---|---|---|
| A link state | 7 | | D controls | 3 |
| B device buffer and gated upload | 12 | | E scenario switch and dose tooling | 5 |
| C sync arm and plan_sync wiring | 18 | | F proofs | 10 |
**Total about 55 h (range 45 to 65), roughly 4x the 12 h limit.** A 12 h slice fits only for A plus E and their off-identity proofs. Recommended staging: A+E (~12 h), then B with FIFO gating (~14 h), then C and F, each gated by its own off-identity proof.

## New dose (distinct matched affected questions, matched across nested cells), E
| rule | s4 t0 | s4 1to3 / 3to5 | s5 t0 | s5 1to3 / 3to5 | matched |
|---|---|---|---|---|---|
| centre 540 (committed) | 540 | 1 / 2 | 540 | 1 / 3 | 7 |
| **proposed A**: max distinct questions of the k=5 prefix, band [270,810], 0.5 s grid | 480 | 2 / 2 | 545 | 2 / 3 | **9** |
| unrestricted [0,1080] | 30 | 3 / 2 | 545 | 2 / 3 | 10 (t0 in run warm-up, not recommended) |
**Caveats: the rule reads the trace's future questions (legal for scenario design, the policy never sees it) but it selects the window that maximises dose, so the dose is by construction and is not an effect size. The s4 optimum is a 2 s plateau (480 to 482 s); only 15 percent (s4) and 40 percent (s5) of band start times give a non-zero dose at both steps. The gain over centre is +2 matched questions.**

## Which channel can carry an effect, per arm
- **Evidence-overlap:** FIFO arms and baselines receive the evidence 0.853 s after reconnect, so their drain-bounded dose is 0 (as in 722c449f). Only the GATED sync arm can show a missed-evidence effect.
- **Asked within the catch-up interval:** 0 distinct within 4.4 s at every rule and seed; 0 to 2 within 30 s; non-zero only if the gated arm defers far-off devices.
- **Burst on others:** about 1 recall plus 27 monitor (s4) and 0 plus 18 (s5) exposed within 5 s of reconnect, the same at k=1,3,5. This model-based screen (D162: the fifth served victim 4.37 s) is the channel the FIFO-versus-gated contrast rests on; it is not a measurement.

## Design choices NOT stated by the ruling (to be ruled)
1. Combination of the four priority factors: (i) lexicographic, (ii) scalar w_d*P(question before catch-up)/(cost+harm), (iii) slack ordering by next-question time minus catch-up time, (iv) marginal on-time gain per decision period in D177 currency (recommended).
2. Window rule and band restriction; same t0 per seed.
3. New Observation field versus extending RecallQuery versus adding robots to `streams` (the last changes baselines).
4. Whether post-reconnect frames upload immediately or behind the backlog (append-only KV forces oldest-first prefill, D148/D152).
5. Questions asked inside the outage: device-only (D242 behaviour).
6. `plan_sync` accuracy input: no committed value for question-first; the planner substitutes cloud RECENT.
7. Mixed per-device links (D226 1b) in or out: with uniform 13.6 Mbps the upload term is under 1 s.
8. Which existing signal is the saturation guard for background sync.
9. A new E-id (the StudyD266-NESTOUT row exists at EXPERIMENTS.md:340).
