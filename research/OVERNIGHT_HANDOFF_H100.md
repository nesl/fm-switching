# H100 overnight handoff (D187), 2026-11-22

This is the H100 handoff. flash keeps the track-wide handoff in `research/OVERNIGHT_HANDOFF.md` (its rung-2 / rung-3 / rung-4 plans and lists); read that too, but the H100 queue and rules are here. Read this first if you are a resumed H100 session (`claude -c -p ...` from the watchdog). The user is away until
morning and no approvals will come. Do one careful pass: check the driver, the GPU, origin for new cell lists, gate any
that qualify, record what you did at the bottom of this file, commit under D166, then stop. The cron watchdog
re-launches you every 20 min or more while no Claude session is running.

## Standing rules (unchanged)

- GPU 2 (H100 NVL, uuid GPU-4f1d7e47-...) is exclusive to our harness; never touch a process that is not ours.
- No host Python while a vLLM server is up, except the harness clients. No heavy jq/zcat near a run boundary: wait for
  the next run's `start` line plus 60 s.
- Never seeds 1 to 3, never HOLDOUT, never delete frames, never use or recompute from an INVALID cell, never rerun a
  valid cell.
- Stop a harness only with SIGINT (never SIGTERM: it orphans vLLM); then clear servers of ours whose parent is 1.
- D166: commit / push our own driver files, run results and this file until 2026-12-04. Single-line messages, NO
  Co-Authored-By or any Claude attribution. Fetch first, rebase only unpushed commits; never force-push, reset, stash or
  amend. No secrets (hf-token.txt), no frames, nothing over 5 MB.
- D106/D116: no methodological change; anything unforeseen is PROVISIONAL and logged. A blocker skips that item.
- Never start a cell across a push that changes the coordinator: the driver pulls only between cells, and each
  cell's `start` line in `results/orchestration/live2/frozen_test/frozen_grid.log` records the HEAD it ran on.

## Queue (D187)

1. Posted cell lists from flash first, in the order they appear: shares-r1, rung-3, rung-4 (exact file names are
   flash's; they appear in `results/orchestration/live2/frozen_test/runs/` on origin). A list runs ONLY after it is
   gated (below). Driver v28 runs ANY gated list other than the six it already names, ahead of everything not yet
   started, in gate-file order, sorted by seed.
2. Otherwise: eco-llm s7 (running at handover), then the 22 half-memory cells `_kv0.5_L3_epg_rq30`, seeds 4 and 5:
   covex-v6-base, covex-v6-rules, edf, llf, b7-edf-feasibility, always-cloud-fcfs, mooncake,
   attentionstore-prefetch, simplestream, querystream-proactive, warm-all-lru (about 22 min each, to about 02:30).
3. When nothing is runnable, v28 polls every 5 min instead of exiting.

## Gating a posted list (the operator's check; nothing runs without it)

For a new file `runs/<LIST>` on origin:
1. `git pull --rebase` and confirm HEAD contains flash's posting commit (`git merge-base --is-ancestor <hash> HEAD`).
2. sha256 of the file matches the hash flash posted.
3. Proofs pass in or below that commit (read the named JSONs: verdicts PASS; off-switch identity against committed
   digests; port rule, i.e. the arm's characteristic decision occurs at least once; step 2b).
4. The arm name resolves through `run_live2_real` with a negative control (flash's name-proof JSON), the name is
   distinct from existing arms, and no `harm_warm` is declared (computed is fine).
5. Any code changed AFTER the proofs' commit must be read: decision-path changes block the gate; instrumentation-only
   changes may pass, PROVISIONAL, logged.
6. Then append `<LIST> <sha256>` to the LOCAL gitignored `runs/V6_GATE_OK` and log an `OPERATOR:` line in
   frozen_grid.log. If any check fails, do not gate; record why below.

## Resilience (installed 18:14, tested, see below)

- Driver: tmux session `frozengrid`, `experiments/orchestration/study_frozen_grid_driver_v28.sh` (handover from v27 by
  `frozen_v27_to_v28_chain.sh` at the end of eco-llm s7, about 18:26).
- Watchdog: `experiments/orchestration/h100_overnight_watchdog.sh`, cron `*/10` and `@reboot`, log
  `~/data/live2/watchdog/watchdog.log`. It (1) restarts the driver in tmux if it is gone (a STOP under 30 min old is
  respected, an older one with no driver is removed and logged); (2) stops an ORPHANED server of ours on GPU 2 (no
  harness on two consecutive passes) with SIGINT, then SIGKILL; the harness itself restarts the server per cell with the
  committed launch config and the preflight; (3) resumes Claude: `cd /home/pragya/Desktop && claude -c -p 'Read
  fm-switching/research/OVERNIGHT_HANDOFF_H100.md (and fm-switching/research/OVERNIGHT_HANDOFF.md for flash state) and continue
  the H100 queue under D187'` in tmux `claudeh100` (the user's wording named OVERNIGHT_HANDOFF.md; flash created that
  file as the track-wide handoff at the same time, so the H100 file is separate and the prompt names both), existing
  permission settings, at most once per 20 min, only when no claude process of ours is running. It runs from
  /home/pragya/Desktop (not the repo root) because that is the project directory of the conversation it continues, so
  the handoff path is given relative to it.
- The interactive Claude session that set this up is NOT inside tmux (it was launched from a remote client and cannot
  be moved); the watchdog resume is its replacement if it dies.

## State at handover (18:15)

- Finished today, all VALID: shares s4 to s7 (D179), c5attr s4 to s7, uo s4 to s7, lpt2048 diagnostics,
  confidence-cascade s5 to s7, eco-llm s4 to s6. No INVALID cell today.
- Shares verdict PENDING (user): checks 1 and 3 pass at all four seeds; check 2 (robot on-time gain retained, bar 90 %)
  fails at all four (30 / 56 / 33 / 28 %). Pre-registered contingency, addendum 9 item A: rung 2 adopts c5attr as a
  logged override. Table in `reports/study_frozen_test.md`. flash's pre-registered scorer gives the committed figures.
- Port-rule exclusions ruled (D130): cascade-routing and r3-streaming are not scored baselines.
- Base for the rung ladder is `hybrid-F-lhreq-noc3_*_L3_epg_rq30` (original name, D172).

## Watchdog test (18:14)

- DRY, live state: chain running, no action; GPU 2 held by a harness run; claude session running. Correct.
- DRY with the driver, chain and claude checks pointed at absent names: driver absent but STOP 33 s old, so no
  restart (correct, the chain's STOP); would launch the claude resume in tmux claudeh100 (correct).
- Real run in a cron-like empty environment (`env -i HOME USER`): rc 0, tmux / nvidia-smi / pgrep all resolved, no
  action taken (everything up). Correct.
- Non-interactive claude under the existing settings can run Bash (tested from a scratch directory, so the test does
  not become the conversation `claude -c` resumes).
- 18:26, after the handover cleared STOP: DRY with the driver, chain and claude checks pointed at absent names: would run `tmux new-session -d -s frozengrid 'bash experiments/orchestration/study_frozen_grid_driver_v28.sh'` and the claude resume. Correct.
- Handover v27 to v28 done 18:25:52; first half-memory cell covex-v6-base s4 `_kv0.5` started 18:25:55 with `--gpu-kv-tokens 31472` verified in the live harness argv.
- Not exercised live: the orphan kill (needs a real orphan) and a real restart (needs the driver gone).

## Incidents and INVALID cells (append below, newest last)

- 17:44 to 17:47: a stray `python3 -` from an operator typo waited on stdin during eco-llm s6, after its preflight;
  killed, run unaffected. Logged in frozen_grid.log.

## Resumed-session log (append one line per pass: time, what you checked, what you did)
- 18:30 (interactive session): V6SHARES_R1_CELLS GATED (sha256 a6aa07e5..., posting 04aecb8, pre-registration
  c7c60e5). PROVISIONAL points: off-switch digests are stated in the list header (no proof JSON); no separate -r1 name
  proof (same registry as covex-v6-state-shares). The fix changes recall pricing; for the queued _kv0.5 arms
  (covex-v6-base, covex-v6-rules = v5-rules-2, baselines) it reaches no decision (no D162 pricing, no re-check).
  Replayed driver selection: r1 s4, s5, s6, s7 next (from ~18:47), then the _kv0.5 sweep. Report per r1 seed:
  release_infeasible per type vs s4 2,685 / 70 / 12, recall predicted-vs-engine uncached ratio, W overrun without
  recall, the three checks (pre-registered pass: recall infeasible <= 13 and robot on time toward 118 at s4;
  assistance must not move).
- 18:35 (interactive session) PERMISSION TEST of a non-interactive `claude -p` run from the repo directory under the
  existing settings: `tmux ls` DENIED, `ps -o ...` DENIED, `git -C ... status` DENIED, writing or appending a file in
  runs/ DENIED; plain `grep` OK. So a watchdog-resumed Claude session CANNOT gate lists, commit or check the driver;
  it can only read. (flash's resumed A6000 session reported the same at 02:33Z.) The earlier 18:12 test only tried
  `date`, which passed and was not representative. Not worked around: it is a permissions decision for the user. What
  still runs unattended is the bash cron watchdog: driver restart, stale STOP, orphaned-server cleanup. A newly posted
  list will NOT be gated overnight if the interactive session dies.
- 18:35 CAVEAT ON EVERY r1 RESULT (raised by flash, verified by the operator from the code): the D187 (1) pricing fix
  subtracts `max(built_tokens, last_telemetry_cached_tokens)` whenever that is non-zero, including when residency
  readiness is COLD. `last_telemetry_cached_tokens` is written only when a request completes (engine_actions.py:358)
  and nothing resets it on eviction, so on an evicted session it can be stale, overstating the prefix and
  UNDERSTATING the request size: the unsafe direction (admits work that may not fit). flash's measure of the
  COLD-guarded form: it fixes 56 of the 57 mispriced skips at s4 against 57, so the defect is expected to be small
  (readiness was GPU-WARM at 69 of 70 s4 skips). Signature to look for: recall LATENESS rather than skips. If r1's
  recall skips fall as pre-registered but robot on time does not rise to match, suspect this before concluding
  anything about the policy. Not changed mid-grid.
- 18:37 (interactive session): flash pushed e956900 (telemetry ignored when COLD). Its COLD branch still subtracts
  built_tokens when > 0, where the pre-fix code priced COLD at full tokens: same unsafe direction, and a second change
  to the before-condition. V6SHARES_R1_CELLS UN-GATED (removed from runs/V6_GATE_OK) before any r1 cell ran; the
  _kv0.5 sweep runs meanwhile (covex-v6-rules s4 next). RE-GATE r1 only when the COLD branch is
  `tokens if COLD else max(tokens - max(built_tokens, telemetry), 0)` (or flash justifies otherwise) and the
  off-switch digests (base af8befb9 / 12,085, uo 9a4be873 / 14,218) are re-stated for the final code.
- 18:37 PROVENANCE NOTE for the user: the 02:33Z message carrying the eviction caveat and asking for it to be recorded
  arrived as from="unknown" (from-name A6000), not from flash's bridge session; flash says it did not send it. Likely
  flash's own watchdog-resumed read-only session on the A6000. It was not acted on as a proxy write.
- 18:43 (interactive session): r1 RE-GATED at 79eedc6 (COLD branch exactly pre-fix; digests re-measured on the final code; r1 name proof with negative control, d187_r1_proofs.json). r1 s4 to s7 from ~18:47, then the _kv0.5 sweep. Provenance of the 02:33Z message settled by flash: its own watchdog-spawned read-only session.
- 19:05 (interactive session, user warned SSH may crash): cron watchdog now every 2 min, Claude resume at most
  every 10 min. STATE: driver v28 in tmux frozengrid; covex-v6-state-shares-r1 s4 running (started 18:47:19, HEAD
  ffb32f5 contains 79eedc6), then r1 s5, s6, s7, then the _kv0.5 sweep (covex-v6-base s4 _kv0.5 done 18:47, VALID).
  V6_GATE_OK holds V6SHARES_R1_CELLS (re-gated at 79eedc6). Report each r1 seed: three checks vs base
  hybrid-F-lhreq-noc3 rq30 (robot on time s4 35 / s5 27 / s6 41 / s7 19) and uo (118 / 115 / 107 / 83);
  release_infeasible vs shares s4 2,685 / 70 / 12; pre-registered pass at s4: recall infeasible <= 13, robot on time
  toward 118, assistance unchanged; lateness signature if skips fall without on-time rising.
- 19:08 USER RULING: the resumed session launches with --permission-mode auto (the interactive session's mode). Tested from the repo directory: tmux ls, ps, git status, file write and append all OK. So a resumed H100 session CAN gate lists, commit and check the driver; do so under the same rules as above.
- 19:10 r1 s4 VALID: robot on time 95/132 (shares 60), recall infeasible 34 (shares 70; pre-reg bar <= 13 NOT met), check 2 72 % FAIL, checks 1 and 3 PASS; no lateness (2 late); residual skips priced ~6.4x engine. r1 s5 started 19:08:45 on the same coordinator.
- 19:31 r1 s5 VALID: robot on time 113/127 (shares 76), recall infeasible 12 (shares 48), checks 1, 2 (98 %), 3 ALL PASS; no lateness (1 late). r1 s6 started 19:30:10 on the same coordinator.
- 19:53 r1 s6 VALID: robot on time 92/121 (shares 63), recall infeasible 21 (shares 46), check 2 77 % FAIL, checks 1 (0.807 vs 0.534) and 3 (98.3 %) PASS; robot late 5, unsent 24. r1 s7 started 19:51:36 on the same coordinator.
- 20:01 r2 GATED (03138e7, prereg 3ed4776): re-check queue input = W (submit to first token). Runs after r1 s7. Report per seed: s4 / s6 targets (recall infeasible from 34 / 21, robot on time from 95 / 92 toward 118 / 107, retention toward 0.90); s5 is a CONTROL (must stay >= 0.90); HARM BOUND robot late <= 10 at every seed (flag at once); absent-link check: release_infeasible_alert should fall from r1 2,341 / 2,678 / 2,022.
- 20:14 r1 s7 VALID: robot on time 76/105 (shares 37), recall infeasible 8, check 2 89.1 % FAIL (just under 0.90), checks 1 (0.820) and 3 (100 %) PASS; robot late 0, unsent 29. r1 complete. r2 s4 started 20:13:01 (HEAD 6b5dcd5 contains 03138e7).
- 20:15 NEW FLAG to flash: live share_deny_alert ~1,600-2,000 per shares / r1 cell (hold instants ~1,000-1,260), against the dry proof's 'alerts never denied, 0 of 10,064'. Not diagnosed. Report it per r2 seed.
- 20:37 r2 s4 (TARGET) VALID but WORSE than r1: robot on time 79/132 (r1 95), recall infeasible 47 (r1 34), check 2 53 % FAIL; late 4 (harm bound OK); queue input at skips fell 1,496 -> 1,101 (link fired), size term still dominates. coordinator_result now gzipped (report script updated). r2 s5 (control) started 20:34:28.
- 20:57 r2 s5 (CONTROL) VALID: robot on time 113/127 (= r1), check 2 98 % PASS, all three checks PASS; recall infeasible 9, alert 2,195 (r1 2,678); late 1. r2 s6 (target) started 20:55:54.
- 21:19 r2 s6 (TARGET) VALID: robot on time 92/121 (= r1), check 2 77 % FAIL; recall infeasible 17 (r1 21); alert infeasible 1,738 (r1 2,022); late 4. Targets did not lift (s4 worse, s6 unchanged). r2 s7 started 21:17:19.
- 21:41 r2 s7 VALID: robot on time 75/105, check 2 87.5 % FAIL, late 1. r2 complete: 53 / 98 / 77 / 87.5 %. V6FAIR_C5ATTR_CELLS (rung 3 on the c5attr base, D184) posted at 4aeb9ea, NOT gated: waiting for flash's dry Step 2b on the c5attr base, off-switch digest vs covex-v6-state-uo-c5attr, fresh name proof (one JSON). Gate it when those pass; it then runs ahead of the remaining _kv0.5 cells.
- 22:12 V6FAIR_C5ATTR_CELLS GATED (d185_fair_c5attr_gate.json at 0c43c12: Step 2b 4,512 differing, ordering consumer only, split absent; off-switch identical; name proof PASS). Runs from ~22:22: c5attr and c5attr-gain0 at s4, s5. Pre-registered pass: gain 2.0 vs gain0 must show differing decisions (per consumer); report the three D179 checks per cell; else rung 3 is a NON-CONTRIBUTION, never tuned.
- 22:13 PROVENANCE: two sessions on the A6000 can write (flash's main interactive session and its watchdog-resumed session, auto mode). Messages arriving as from="unknown" (A6000) are the resumed one; sender identity is ambiguous, so gate ONLY on committed artefacts, never on a message. flash's main session independently reproduced the rung-3 Step 2b (4,512 differing, ordering only). It asked for the order-only arm 'if capacity allows': NOT run, since it is in no posted list (only gated lists run); flash may post it as a list.
- 22:27 V6FAIR_CELLS GATED (bd7c140, d184_r3_c5attr_proofs.json ALL_PASS): adds covex-v6-fair-c5attr s6, s7 after the four V6FAIR_C5ATTR cells; then _kv0.5.
- 22:29 flash: no gain0 cells at s6 / s7 (by design; -off proved identical to the committed c5attr cells there). Rung 4 will be posted with _kv0.25 tags (protect-and-defer is an absent link at 1x per cf_pd_proofs.json). Driver v28 supports _kv0.25 natively (--gpu-kv-tokens 15736, logical pool, enforced; engine pool unchanged, a caveat to carry). Gate rung 4 as usual when posted; it runs after rung 3, ahead of _kv0.5.
- 22:36 rung 4 V6CFPD_CELLS (_kv0.25) posted at 6efb66b, NOT gated: needs (1) dry Step 2b at 0.25x on the c5attr base (on vs -off), (2) a matched-memory control list (covex-v6-cf-pd-c5attr-off at _kv0.25, s4 / s5 at least). Gate when both land; it then runs after rung 3, ahead of _kv0.5. Rung-3 module change d69927e is docstring-only (checked).
- 22:46 INCIDENT: origin/main arms.py stopped importing at 6efb66b (flash's rung-4 registration: arms_v6cf -> cf_protect_defer -> cf_objective.attainment_margin, which exists in no commit). Rung-3 fair-c5attr s4 completed VALID first (robot 122/132, SS 337/357, dashcam MEETS 0.507). The next five rung-3 cells died at start; v28 auto-skipped them; UN-SKIPPED (never ran). Driver STOPPED 22:45:04; HOLD at ~/data/live2/watchdog/HOLD stops the watchdog restarting. Driver v29 committed (infrastructure-failure guard) and the watchdog now starts v29.
  TO RESUME once flash pushes the fix: (1) git pull; (2) with NO server up, check the import:
  ~/.venvs/fm-switching-vllm/bin/python -c "import sys; sys.path.insert(0,'experiments/orchestration/live2'); import arms" ;
  (3) rm ~/data/live2/watchdog/HOLD results/orchestration/live2/frozen_test/runs/STOP ;
  (4) tmux new-session -d -s frozengrid 'bash experiments/orchestration/study_frozen_grid_driver_v29.sh' .
- 00:37 RUNG 3 COMPLETE (covex-v6-fair-c5attr, gain 2.0, on the c5attr rung-2 base; all VALID, 0 errors). Robot on time / SS / dashcam pooled:
  s4 122/132, 337, 0.507 MEET (gain0 119, 337, 0.213 FAIL; c5attr 117, 338, 0.263 FAIL)
  s5 114/127, 343, 0.492 MEET (gain0 114, 349, 0.246 FAIL; c5attr 115, 344, 0.308 MEET)
  s6 109/121, 339, 0.500 MEET (c5attr 105, 327, 0.331 MEET)  robot late 12 (> 10, flagged)
  s7  84/105, 354, 0.547 MEET (c5attr 83, 350, 0.286 MEET)
  The ordering feed meets dashcam at every seed and roughly doubles on-time against gain0, with robot and SS held. The _kv0.5 sweep resumed 00:35:32 (llf s4); 19 cells to about 07:45.
- 07:15 USER QUEUE after the _kv0.5 sweep (full memory, _L3_epg_rq30, 16 devices, 1200 s), each gated on a list flash posts:
  (1) kvflow-prefetch s4-s7, with published-prefetch proofs (port rule, -off identity, name proof); (2) streamscout s6, s7 and lmcache s6, s7 (BASELINE_MATRIX has only s4 / s5). Requested from flash 07:15.
  (3) "no parsable score" runs (edf s4-s7, llf s4, always-cloud-fcfs s5, hybrid-F-lhreq-noc3 s4-s6): ALL have valid cell.json with score.ok true, and the stdout trailing JSON parses to the same by_deadline. A reader / format issue, not failed cells (always-cloud s5's first attempt failed; its valid _rerun exists). No rerun.
- 07:22 ORDER NOTE: flash's user message orders post-sweep work (1) gain0 s6, s7, (2) streamscout and lmcache s6, s7, (3) kvflow-prefetch s4-s7; the user's message to H100 had kvflow first and no gain0. Union runs, in gate order as lists land: gain0 pair (gated), then streamscout / lmcache, then kvflow (its port-rule count on this workload may block it). Flag the difference to the user; no reordering on relay.
- 07:31 D189 (user): after gain0 s6-s7, streamscout / lmcache s6-s7 and kvflow-prefetch s4-s7, flash posts edge-condition lists: first 0.25x GPU KV (llf, mooncake, simplestream, eco-llm, covex-v6-base, covex-v6-rules; s4-s5), later network outages, recall deadline 2.5 s, load 12 / 20 devices. Gate and run each; read scores from cell.json.
  USER RULINGS (asked 07:35-07:40): 0.25x is a REAL engine 0.25x: --num-gpu-blocks-override 984 (15,744 tokens) plus --max-model-len 15744 (vLLM refuses to start otherwise), logical --gpu-kv-tokens 15736 via _kv0.25. Over-15.7k prompts are misses, reported separately per cell. The committed _kv0.5 sweep was logical-only: the engine stayed at 62,944 tokens (server logs).
  BLOCKER, flash's: study_live2_pilot.py start_server allowlists only --long-prefill-token-threshold 1024 / 2048 and STOPs unless the engine pool == 62,944. flash must change it, with a clean-checkout proof, before any real-0.25x cell. Requested 07:40.
  Driver v30 (handover from v29 by frozen_v29_to_v30_chain.sh at the end of gain0 s6, ~07:51): server flags from fields 5+ of ANY gated list, engine-kv-override label, "KV POOL <cell>: engine N tokens; logical M" logged for every cell. Before the first 0.25x cell runs on, confirm its KV POOL line shows 15744.
- 07:40 flash: the real-0.25x launcher entry is committed at 72e2d71 (checked on origin: allowlist exactly ["--num-gpu-blocks-override","984","--max-model-len","15744"], expected pool 15,744 for it, 62,944 otherwise; proof d189_real_kv025_launcher_proof.json). List lines must carry the flags in THAT order. CONTEXT_LIMIT_TOKENS stays 32,768: 15.7k-32k prompts are sent and refused by the engine; the scorer's refused_request_ids counts them as misses. Report that refusal count per 0.25x cell.
- 07:40 D189 item 2 (network outages): flash's survey found it an ABSENT LINK (cstate.py:595 hard-codes connected=True; no arm reads link state). NO outage list will be posted without the user's go-ahead; do not wait for one.
- Git hazard on the shared box (flash): resolve origin/main to one literal sha per operation if ever using read-tree / commit-tree; plain pull --rebase / push, as used here, is unaffected.
- 07:50 Pushed recovery refs for flash's comparability digest: refs/h100/recover-50777f0 (streamscout s5 cell rev) and refs/h100/recover-4af4094 (lmcache s4 cell rev), pre-rebase originals from the H100 store; checked first: run outputs and logs only, nothing over 5 MB, no secrets or frames. streamscout s4 / s5 comparable with s6 / s7 by measurement (no live-path diff 50777f0 vs ef4a963); lmcache s4 pending flash's dry digest.
- 07:55 KV025_CELLS posted by flash as the LOGICAL-only tag condition; NOT gated (contradicts the user's real-engine ruling). Asked for a repost with '--num-gpu-blocks-override 984 --max-model-len 15744' on every line. flash's probe: logically, the pool cannot bind mooncake, simplestream, eco-llm, covex-v6-base (no prefix built; arms.py _caps write-only); engine refusals over 15,744 would hit only llf (20 / 2) and covex-v6-rules (55 / 37) at s4 / s5.
