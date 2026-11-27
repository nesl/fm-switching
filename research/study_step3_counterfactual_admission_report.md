# STEP 3 BUILD REPORT v3 (user ruling D324: arrival window = queue wait + service time)

Status: BUILT AND DRY-CHECKED, NOT PUSHED, NO CELL, NO GPU, nothing committed. Previous reports kept: `REPORT_v2.md` (D320) and `REPORT_v1.md`. Sections 3 (definition) and 5 (replay) of v2 are replaced by sections 1 to 3 below; v2 sections 2, 6 to 9 stand except where noted.

## 0. A CORRECTION TO v2 THAT CHANGES HOW (a) AND (b) READ
B's load-aware estimate is `first_token_s(u, ahead) = INTERCEPT_S + PER_UNCACHED_S x u + PER_QUEUE_S x ahead` (d162_price.py:90; constants :46-48; B calls it as `LA.loadaware_est(u, ahead)` at hybrid_arm.py:553-554 and la_arrival_admission.py:85). Its first two terms are the admitted request's own SERVICE time (queue empty), its third term is the QUEUE WAIT (`PER_QUEUE_S x queued_uncached_ahead`). The window I used in v2, `min(est_loadaware, HORIZON_WARM_CAP_S)`, therefore ALREADY contained the queue wait: v2 labelled it "service time (3 to 4 s)", which was wrong; it was queue wait + service. So the D324 rule (queue wait + service, capped at 120 s) is numerically the v2 rule: every v2 replay and dry number is unchanged (checked: the dry digests of `-cf` are identical to v2, kv 0 `2f00254f` and kv 8000 `fe864ac2`, and the replay admits are identical: 2, 1, 11, 9, 13, 19, 10). What is new is the genuinely service-only window, which D324 asks me to keep as variant (b): v2 never ran it (v2's "full 120 s" sensitivity was a different, longer window). The variant is built and measured below.

## 1. What was built (D324)
- `cf_forfeit.arrival_window(service_s, wait_s, cap_s, mode)` (cf_forfeit.py:154; `WINDOW_MODES` :151): 'queue_service' (default) = min(service + wait, cap); 'service' = min(service, cap). Empty queue: both equal.
- In the arm (arms_v6cfstep3.py:186-195): `service = DP.first_token_s(u, 0)`, `wait = DP.first_token_s(u, queued_ahead) - service` (= PER_QUEUE_S x queued_ahead, d162_price.py:48,90), `queued_ahead` = `la_arrival_admission.queued_ahead(obs)` (:72, the in-flight uncached tokens B itself reads, hybrid_arm.py:553), cap = `cf_cost.HORIZON_WARM_CAP_S` 120 s (cf_cost.py:126, the FUTURE horizon). The mode is a constructor option `cf_window_mode`; both quantities are logged per decision (`queue_wait_s`, `service_s`, `arrival_window_s`). No new constant; no new switch (the D320 `live2_cf_harm_arrivals` stays the only on/off, default OFF).
- Variant arm `covex-v6-fair-final-cand-cf-w0` = the full arm with the service-only window (registered in arms_v6cfr3.py with the other step-3 arms). `-cf` is queue wait + service; `-cf-h0` is still the OLD harm.
Staged blobs: cf_forfeit.py 3326d9fb, arms_v6cfstep3.py dd8977b1, tests/test_cf_forfeit.py 9f37aca5, arms_v6cfr3.py bcb63c08 (on origin 9a085d0d's file); arms_final_ladder.py d4d86158 and coordinator.py bd72a8f9 unchanged.

## 2. Replay, seven cells (w_d = 1; `s3/replay_cf3.py`, `s3/replay3_out.txt`; max |service + wait - est_loadaware| over all rows 5e-07, so the decomposition is exact)
In-set = rejects in the resident set with a priced future. Admitted fraction = admits / in-set. Twin-on-time and saveable as in v2.
| cell (in-set n) | window (a) queue wait + service: admit (frac), twin on time, saveable | (b) service only: admit (frac), twin on time, saveable | (c) old HARM: admit (frac), twin on time, saveable |
|---|---|---|---|
| 1x la-er (5) | 2 (0.40), 2, 1 | 3 (0.60), 3, 1 | 5 (1.00), 5, 3 |
| 1x pwire (1) | 1 (1.00), 1, 0 | 1 (1.00), 1, 0 | 1 (1.00), 1, 0 |
| halved la-er (23) | 11 (0.48), 1, 0 | 14 (0.61), 1, 0 | 21 (0.91), 1, 0 |
| halved pwire (15) | 9 (0.60), 0, 0 | 9 (0.60), 0, 0 | 11 (0.73), 1, 0 |
| n20 la-er (68) | 13 (0.19), 1, 2 | 16 (0.24), 2, 3 | 26 (0.38), 4, 4 |
| n20 pwire (48) | 19 (0.40), 2, 2 | 19 (0.40), 2, 2 | 31 (0.65), 5, 4 |
| n32 la-er (87) | 10 (0.115), 0, 0 | 14 (0.16), 2, 0 | 33 (0.38), 4, 0 |
HARM and FUTURE magnitudes over the in-set priced rows (median / p90):
| cell | FUTURE | HARM (a) | HARM (b) | HARM (c) old |
|---|---|---|---|---|
| 1x la-er | 2.06 / 2.94 | 1.37 / 1.93 | 1.28 / 1.62 | 0 / 0 |
| 1x pwire | 2.27 / 2.27 | 1.52 / 1.52 | 1.37 / 1.37 | 0 / 0 |
| halved la-er | 2.63 / 3.96 | 1.91 / 2.77 | 1.67 / 2.47 | 0 / 0 |
| halved pwire | 2.12 / 4.05 | 1.41 / 2.05 | 1.24 / 1.77 | 0 / 0 |
| n20 la-er | 0.38 / 2.27 | 0.06 / 1.93 | 0.02 / 1.55 | 0 / 0 |
| n20 pwire | 1.35 / 4.69 | 1.29 / 2.94 | 0.92 / 2.69 | 0 / 0 |
| n32 la-er | 0.26 / 2.51 | 0.18 / 2.66 | 0.07 / 2.08 | 0 / 0 |
Queue wait inside the window (in-set median / p90, s): 1x 0.24 / 0.58; halved 0.54 / 2.1 to 2.6; n20 3.7 / 13.8 (la-er), 0.76 / 11.4 (pwire); n32 3.8 / 17.5. Window (a) median against (b): n32 5.4 s against 1.8 s, n20 5.3 against 2.0 (la-er), 1x and halved 3.4 to 4.5 against 3.0 to 3.8: the queue wait lengthens the window most exactly where the queue is long.
READING. (a) admits fewer than (b) in every cell where they differ (1x la-er 2 against 3, halved la-er 11 against 14, n20 la-er 13 against 16, n32 10 against 14) and both admit far fewer than the old HARM (c). KEY CHECK stays MET under (a): n32 11.5 percent of the in-set rejects (3.7 percent of all 270 base rejects), n20 19 and 40 percent. Under (b) it is also met (24 and 40 percent at n20, 16 percent at n32); at n32 the 4 extra admits under (b) include 2 that were on time in the twin and 0 saveable later asks. Total new converts: (a) 65, (b) 76, (c) 128; on time in the twin: (a) 7, (b) 11, (c) 21; saveable later asks: (a) 5, (b) 6, (c) 11.

## 3. Dry checks redone
- OFF identity (1,200 s, n16 3:11:2, digest equal to the candidate `covex-v6-fair-final-cand`): `-cf-off` equal at kv 0 (`9ba39360`) and kv 8000 (`16641a99`). `-cf-a0` (FUTURE 0): kv 0 equals the candidate; kv 8000 equals `-cf-pd` (`8ac0fe56`), the arm with protect-and-defer alone (protect-and-defer acts at kv 8000). `-cf-pd` equals the candidate at kv 0.
- Step-3 arms (first differing decision against the candidate: row 905, t = 181.6, a B decline becomes a release, in all of `-cf`, `-cf-w0`, `-cf-h0`, `-cf-a`): kv 0 digests `-cf` `2f00254f` (23 admitted), `-cf-w0` `31ec8ad0` (25 admitted, +2 against the queue-wait window), `-cf-h0` `3ba025a8` (28), `-cf-a` `66093870`, `-cf-r` `60be2d7d`; kv 8000 `-cf` `fe864ac2` (8), `-cf-w0` `0415228b` (9), `-cf-h0` `59c98299` (11). Dry magnitudes (in-set priced rows, live weights): kv 0 `-cf` HARM median 1.87 p90 3.38, FUTURE median 6.73 p90 12.5, wait median 0.31 s, service 3.76 s, window 4.2 s; `-cf-w0` HARM median 1.69, window 3.69 s. The dry queue is light (no real latency), so the wait term is small there; the replay is where it matters.
- Unit tests: 23 pass (`tests/test_cf_forfeit.py`): the 19 earlier, including the full-queue test (FUTURE 3.0, ten expected arrivals each losing 0.8: HARM 8.0, gate `net_does_not_exceed_the_bar`, KEEP_REJECT) and its light-load twin; plus 4 new window tests: empty queue gives the same window in both modes; a non-empty queue (30,000 queued tokens, u 10,000) lengthens the window by exactly the wait and the window equals `first_token_s(u, ahead)` (B's est_loadaware); the cap at 120 s and an unknown mode raising; a longer window prices more expected arrivals and more harm. The arm wiring test now also checks `-cf-w0` is 'service' and `-cf` is 'queue_service'.
- Off-identity sweep (all 253 registered arms, tree against origin 9a085d0d, ratio 50:50, 300 s digest): 251 identical, 2 identical errors (covex-v6-cf-pd BaseNotChosen, covex-v6-fair-final-pb unknown arm, both as in every earlier sweep), 0 DIFFERENT. New arms at 300 s: `-cf-off`, `-cf-pd`, `-cf-r`, `-cf-a0` equal the candidate (`d651843b`, 3,274 rows); `-cf`, `-cf-w0`, `-cf-h0`, `-cf-a` all `b4651104`, i.e. the windows and the harm variants coincide in the first 300 s (no arrival veto yet); they separate in the 1,200 s dry (section 3).

## 4. Points for the user (changes from v2)
A. The window question is closed: D324's window is what v2 measured, the service-only reading is now a real variant. If the service-only window is preferred it is `cf_window_mode='service'` (arm `-cf-w0`), 76 against 65 converts.
B. Unchanged from v2: most converted asks are hopeless themselves (58 of 65 not on time in the twin under (a)); the value is the 5 saveable later asks; the D319 touch-latch confound at halved memory; the proposed first cells and their expectation text (v2 section 7) are unchanged by this ruling because (a) is numerically the v2 rule (the n20 and halved expectations stand; add the (b) numbers if the user wants the variant run).
C. Merge note unchanged: arms_v6cfr3.py already rebased on origin 9a085d0d's file.

## 5. Files
`s3/tree` (6 paths), `s3/origin`, `s3/dry/*_D_kv*`, `s3/replay_cf3.py`, `s3/replay3_out.txt`, `s3/an_dry.py`, `s3/sweep5050`. v2 text for the unchanged parts: `s3/REPORT_v2.md`.
