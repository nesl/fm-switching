# StudyACC2: per-question 32B accuracy by evidence choice, including long histories, both splits

**Status: INTERIM, 2026-11-19 11:41. GPU run in progress (824 of 1,819 requests); no accuracy numbers are reported
until the run is complete, so that no partial result is read as a finding.**

## 1. Why

flash's StudyEVNEED: history vs recent-only changes the 32B's answer on 14.9 % of S-EMBER questions (helps 8.05 %,
hurts 6.86 %, net +1.18 pp), sending RECENT would remove about 96 % of recall GPU time, but none of StudyR1's 845
questions reaches the history lengths the fleet traces carry (above about 19.4k tokens), and the policy's quality
table (StudyRH4, DEV, n = 243, smallest cell 16) was never checked on EVAL.

## 2. Design as run

- Qwen3-VL-32B, the round-1 server configuration (restarted once), stored D91 JPEG frames in D2 format, the exact
  live recall body (`live2/bodies.py::build_body`, the coordinator's `HEADER_TEXT` and `RECALL_GEN`), greedy.
- Every request is COLD and isolated: a fresh run tag per request, so a fresh cache_salt and fresh image uuids (no
  prefix or multimodal reuse); one request at a time on an otherwise idle engine; idle TTFT is measured to the first
  content token. Verified so far: cached tokens 0 on every request.
- Questions: all 845 StudyR1 questions (602 EVAL, 243 DEV, by the committed split).
- Representations: D2 (every 2-s D2 frame from the session start to the question, as live builds a history) and
  RECENT (the device's last RECENT_W = 120 s, as D2 frames). LONG-HISTORY set: 129 prompts built exactly as the live
  traces carry the history at question arrival (seeds 0, 4, 5, 6 at 64 devices, 600 s; D101 preload plus the batches
  captured by the question; D83 one session), for every question whose trace history exceeds its StudyR1 history,
  deduplicated. 1,819 requests in all; 172 prompts above 19.4k tokens.
- Code: `experiments/sember/study_acc2.py` (prep, run), `study_acc2_analyse.py` (written, runs after the server
  stops). Outputs `results/sember/study_acc2/`.

## 3. Decisions (posted with defaults; no reply by 10:58, so all are PROVISIONAL defaults)

1. RICH = D2 in the live request format: the live body carries exactly the D2 history, so one representation is run.
   StudyR1's RICH (capped at 256 frames, token-budgeted to about 12.6k tokens) cannot be expressed in the live format;
   its committed K1 numbers are the RICH reference.
2. RECENT = the StudyR1 / StudyO recent window (last 120 s) as D2 frames. live2 has two conflicting RECENT
   definitions (467 fixed tokens in cstate vs 0.35 of the history in the eco-llm card), neither of them a frame list.
3. D2 history for the 845 = every D2 frame from session start to the question time.
4. Long set as above (EVAL only, because the fleet traces use EVAL sessions only).
5. Idle, cold, one request at a time.
6. DEV / EVAL from the committed split; bootstrap CIs with 10,000 resamples by question.
7. DEV D2 frames encoded into the D91 store with the Part-1 recipe (StudyR1's 1 fps source frames,
   `study_rh3_inputs.load(path, (352, 256))`, JPEG q88), store-once, marked `acc2_dev` in the encode log: 13,427
   frames for the 70 DEV sessions, up to each session's last question.

## 4. Run record so far

- Prep 11:10 (server down). Server up 11:13:41 (72.9 s). Requests from 11:13:42, about 2.1 s each.
- 824 of 1,819 done at 11:41; expected end about 12:20.
- 3 requests REJECTED by the engine, HTTP 400 "Input length exceeds model's maximum context length (32768)": D2
  histories of 34,109 to 52,009 tokens for questions far into long sessions (one at 1,155 s). The live fleet cannot
  send such a history either; these questions will be reported as "history exceeds context" and analysed separately,
  not dropped silently.
- 2 frames of all prompts are missing from the store (to be listed in the final report).
- TTFT scales with history as expected so far (for example 2,261 tokens 0.49 s, 12,932 tokens 3.2 s, 26,137 tokens
  7.3 s).

## 5. Still to do

Finish the run, then (server down) the analysis: accuracy by representation with CIs, overall and per split, against
StudyRH4's committed rc_accuracy table (`profiles_dev.json`, tables 32B-D2 / 32B-RECENT / 32B-RICH) and StudyR1;
HELPS / HURTS flows by history-length bucket including above 19.4k; the same by category (exploratory); idle TTFT vs
the committed cost curve. Then the D134 queue resumes.
