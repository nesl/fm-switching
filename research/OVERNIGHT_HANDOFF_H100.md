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
