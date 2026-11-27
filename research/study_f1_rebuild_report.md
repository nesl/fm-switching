# F1 (F0 + the counterfactual) rebuild report, 2026-11-27 (build agent report, copied by the flash session; nothing pushed as code)

Staged tree scratchpad f1/tree (11 paths), overlay for dry runs f1/full_f1, patch against the F0 tree f1/diff_vs_f0.patch. Base origin d2c991a2. F0 tree unchanged.

## Paths and blob hashes (experiments/orchestration/live2/)
- cf_forfeit.py 35a82558 (new): the five shared definitions (WINDOW_MODES, arrival_rows, arrival_window, expected_questions, forfeited_future) are removed and re-exported from future_horizon.py (an AST check confirmed the bodies were byte-identical).
- arms_v6cfstep3.py b8e4c8a9 (new): builds on F0's kwargs: make_rung3(..., pb_touch_guard=True, catchup_prefill=True, catchup_value=True, _cls=V6CandCF).
- tests/test_cf_forfeit.py 0ea8c63c (new).
- arms_final_ladder.py f902c180: F0's edits plus a 2-line _cls/_cls_kw hook in make_rung3.
- arms_v6cfr3.py a3fb799e: F0's edits, a _cf3 helper, 8 registry lines on their own lines.
- coordinator.py 3280dee6: F0's edits plus write_cf_decisions (cf_decisions.jsonl.gz sidecar; logging only).
- run_live2_real.py 0baa00ba: 4 keys added to the ON-only header record (live2_cf_protect_defer, live2_cf_forfeit_admit, live2_cf_resident_set, live2_cf_harm_arrivals); every other arm's header unchanged.
- Unchanged from F0: catchup_prefill.py, catchup_value.py, future_horizon.py, tests/test_catchup_value.py.
Arms registered: -cand-tl-sync-cf (F1); -cf-a, -cf-r, -cf-pd (one-factor); -cf-off (all cf switches off = F0); -cf-a0 (FUTURE forced 0); -cf-h0 (old HARM); -cf-w0 (service-only window). Window default: B's est_loadaware used once, capped at the 120 s horizon; no new constant; every cf switch default OFF.

## Merge with the eager arm
The eager tree differs from F0 only in arms_v6cfr3.py (a factory after r3candtlsync and one registry line); F1's edits do not overlap. Combined file f1/combined/arms_v6cfr3.py (blob 60101a7d) = F0 + eager + F1. F0 + eager window: use the eager tree's file. Later F1 window: the other 10 paths from f1/tree plus the combined arms_v6cfr3.py.

## Dry checks (n16 3:11:2 at 1,200 s plus an n20 outage replay on the D332 placement k14 d188 t0 483.5 R 671.5 _qp; no engine latency)
1. -cf-off = F0 = cand-tl: no outage digest 16641a99a26a3465 (kv 8,000) and 9ba393601bf319b4 (kv 0), 0 rows differ; n20 outage: -cf-off = F0 at kv 8,000 (91aeb2a5f9e3940b) and kv 0 (cfb5baa3c2804d39).
2. OFF sweep (300 s at 50:50): 262 names in the F1 overlay against the origin reference of 253: 253 identical, 0 differ; the only additions are 9 arms (F0 plus the 8 cf arms); against the F0-final overlay 254 of 254 identical. Same digest as F0: -cf-off, -cf-a0, -cf-pd, -cf-r (d651843b64b2692e); different: -cf, -cf-a, -cf-h0, -cf-w0 (b465110476935eec).
3. n20 outage replay, F1 against F0: 13,195 rows differ at kv 8,000 (first at row 1,193, t = 181.1 s) and 12,672 at kv 0 (same first row). The counterfactual acts on B rejects at any time, not only after reconnect. Port-proof (kv 8,000): 150 B rejects considered, 15 admitted; 2,813 touches dropped outside the resident set; 106 set rotations; protect-and-defer acted (9 protects, 8 request defers); gates: 91 not in resident set, 19 next question beyond horizon, 13 net not above the bar, 7 no question estimate, 5 no future gain. kv 0: 137 considered, 27 admitted, 3,305 touches dropped, 111 rotations. S2 still fires inside F1 (73 releases kv 8,000; 94 kv 0). Variants: -cf-h0 admits 21, -cf-w0 admits 16, -cf-a0 admits 0 and collapses to -cf-pd (698c972dd15bb7dd) as designed.
4. Seven-cell committed replay NOT repeated (decision code unchanged apart from the arm base and the import move; F1's n16 no-outage digests equal the step 3 digests on the candidate because F0 is inert without an outage).
5. Tests pass: test_cf_forfeit 23 (incl. 'FUTURE large, queue full, HARM blocks' and the window tests), test_catchup_value 12, catch-up prefill 6, pacing 9, busyx 10, question priority 8, touch guard 18.
6. Interaction: one expected_questions function feeds both the admission FUTURE and the S2 gain (same on-time curve and est_loadaware). NOT netted against each other within an epoch: both can credit the same robot's future. In the dry admissions fall at t = 181 to 447 s and at 1,021 and 1,024 s; S2 evaluations are logged only for t = 671.6 to 772.7 s (the log caps at 4,000 rows): 0 of 15 admits coincide with a logged release: not a proof that none coincide later. Named limitation, not fixed.

## Proposed first F1 cells (not queued); comparator F0 (cand-tl) at the same seed and tag
Tags: 1x `covex-v6-fair-final-cand-tl-sync-cf 16 <s> _L3_epg_rq30_qp`; n20 `... 20 <s> _c3-11-2_L3_epg_rq30_qp`; halved `... 16 <s> _kv0.5r_h0.5_L3_epg_rq30_qp` (+ halved args). Header check: all four live2_cf_* keys, live2_catchup_prefill_value and live2_pb_touch_guard true.
Expectation (F1 minus F0; D330/D331 pooled CI form): 1x no-harm: the cbd CI and the cloud on-time CI each include 0 or are positive; exercised only if cf3_admitted or dropped touches > 0, else UNEXERCISED. n20: cbd not below F0 (CI includes 0 or positive). Halved: the same; report touches issued over considered beside cbd (the latch is run-dependent). User addendum: converts were on time in the rung 3 twin only 7 of 65 times, so neutral to slightly negative is the likelier outcome and the n20 half the likelier to fail. Any miss = FAIL, recorded; F0 is then the final arm.

## Not verified
Live magnitudes (no engine latency in the dry). F0 shows 91 releases in this run against 87 in the S2 report (guess: the _qp setting; not re-read). Admissions before the outage start at t = 181 s, so the counterfactual's effect is not confined to the outage window; the windowed network readout for F1 needs cf_decisions.jsonl.gz rows (time, gate, terms).
