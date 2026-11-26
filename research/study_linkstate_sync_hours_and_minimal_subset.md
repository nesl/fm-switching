# LINK-STATE AND SYNC BUILD: PER-PART HOURS AND THE MINIMAL SUBSET (2026-11-26T01:27Z). Estimate only, nothing built. Minimal subset is still 48.5 h, so only stage 1 (10.5 h) is under the 12 h bar.

**Register: the sub-item hours are an ALLOCATION of the scoping report's part totals (A7 B12 C18 D3 E5 F10 = 55), made WITHOUT reading the code sites; they are not measurements.** N = new code, R = reuse. Totals are flash CPU, build plus proof.
## (a) Per-part
| part | sub-items (h) |
|---|---|
| **A 7** | A1 emulator emits connectivity events 1.5 N; A2 coordinator ingest plus epoch 1.5 N; A3 cstate per-device link table 1.0 N; A4 new Observation field, validation, scrub tests 1.5 N; A5 off-identity proof 1.5 N |
| **B 12** | B1 trace held semantics 1.5 N; B2 emulator held backlog plus sync_offer 3.0 N; B3 sync_pull reply releasing the oldest-first prefix through UplinkQueue 2.5 N; B4 baseline auto-release flag 1.0 N; B5 cloud belief cum_tokens correction plus D2 header re-attribution 2.5 N; B6 prompt-builder frame_refs check 1.5 N |
| **C 18** | C1 arm subclass plus ranking 3.0 N; C2 causal question-rate estimate 1.0 R; C3 catch-up cost (upload plus D162 prefill) 2.5 N; C4 current-queue harm term, deficit-weighted 3.0 N; C5 background scheduling under the saturation guard 3.0 N; C6 plan_sync wiring (accuracy input, D177 currency read) 3.5 R plus glue; C7 priority-form implementation 2.0 N |
| **D 3** | D1 FIFO control 1.0 mostly R; D2 naive-recovery control 2.0 N |
| **E 5** | E1 placement switch 2.5 N; E2 dose tooling (window rule, grid, matching) 2.5 N |
| **F 10** | F1 switch-off byte identity every arm 2.5; F2 outage-off identity of our arm against rung 3 1.5; F3 connected live with a named read site 1.0; F4 positive control (sooner-expected device syncs first; FIFO reproduces arrival order) 2.0; F5 device history unchanged 1.0; F6 cloud history gains the backlog only after upload 1.0; F7 held-backlog conservation plus D2 header 1.0 |
**NOT in the 55 h: merging the NESTOUT change set (only in the handoff; trace.py 1,455 lines against 1,216 on origin). Guess 2 to 4 h, unverified.**
## (b) Minimal subset (the user's definition): 48.5 h, 36.5 h over the bar
IN: A1-A5 (7.0), all of B (12.0), C1-C4 and C7 (11.5), C6 (3.5, needed for question-first/wait/device), D1+D2 (3.0), E1 (2.5), F1-F6 (9.0). OUT (6.5 h): C5 background scheduling 3.0, E2 dose tooling 2.5 (reuse the centre-540 window, 7 matched questions), F7 1.0. **B and C are the core, so no subset containing a gated arm is near 12 h.**
| stage | contents | h | cumulative |
|---|---|---|---|
| S1 | A1-A5, E1, F3: link state plus scenario switch, no policy decision | **10.5** | **10.5** |
| S2 | B1-B6, D1, F5, F6: FIFO-gated baseline, first contrast against baselines | 15.0 | 25.5 |
| S3 | C1-C4, C7, F4: our urgency-ordered arm (device-vs-cloud stubbed to question-first) | 13.5 | 39.0 |
| S4 | C6, D2, F2, F1: plan_sync, naive-recovery control, identity proofs | 9.5 | 48.5 |
Run F1 as a smoke check at each stage and record it formally at S4; each stage's off-identity proof passes before the next starts.
**Cannot work without a ruling or a later item:** (1) question-first needs C6, no committed accuracy value for it exists (the planner substitutes cloud RECENT) and plan_sync's D177 currency status needs a read; (2) questions inside the outage are device-only (D242), ruling needed before S3; (3) the priority-form combination before C7, so C3/C4/C7 sizing is soft; (4) post-reconnect frames immediate or behind the backlog, before S2; (5) without C5 the arm releases only on request, so the burst-on-others channel is exercised only through the request path; (6) the study is meaningful only if E1 plus B give the gated-versus-FIFO contrast on the 7 matched questions, and the thinness of 7 was not re-checked.
## (c) Candidates
**Priority form:** (i) lexicographic (urgency bucket, then w_d, then cost and harm); (ii) scalar w_d*P(question before catch-up)/(cost+harm); (iii) slack ordering, next-question time minus catch-up time; **(iv) marginal on-time gain per decision period in D177 currency minus harm (RECOMMENDED, consistent with D177/D249).**
**Window rule (E2, deferred in the minimal subset):** A = maximise distinct questions of the k=5 prefix within the band [270,810] (t0 480 s at s4, 545 s at s5, 9 matched, dose by construction); B = same picks; unrestricted [0,1080] picks t0 19 to 30 s (run warm-up, not recommended, 10 matched). **Recommended: A, but only after S1, since the minimal subset keeps the centre window and its 7 matched questions.**
