SS2 PROMPT PROFILE (D345 job 2) - full notes. Read from origin/main 8d41c054 (git show / git archive). No repo file
edited, no GPU job, no server request. Everything under scratchpad/ssprof/.

FILES
  ss2_prompt_profile.py   runner + scorer wrapper + summarizer + --dry (self-contained; imports the committed
                          ss2_bench_kit, bodies, cachekeys, scores, _provenance; reads HEADER_TEXT out of coordinator.py)
  dry_harness.txt / dry_offline.txt   --dry output (3 questions per subset x formats A, B, C)
  run_plan.sh             the H100 / Orin command sequence (NOT run)
  ss_text_log.diff        the SS answer-text logging switch, against origin 8d41c054 (coordinator.py, fleet/emulator.py)
  dry_sslog.py, run_dry_sslog.sh, cmp_sslog.py, dry/, dry_proof.txt   the no-GPU proof of the switch
  selftest/               synthetic-row test of scoring + summarize code paths (fake numbers, not results)
  tree_orig/ (origin archive, 1.8 GB of results subset), tree_new/ (patched copy): may be deleted after review

FACTS VERIFIED (beyond the brief)
  * committed SS2 reproduce the FAIR counts per subset, correct = kit score >= 0.5 (episodic_lib.ss2_correctness):
      cloud 32B  refspatial 103/277, rwq_mcq 313/438, rwq_ff 232/327 = 648
      device 4B  refspatial  70/277, rwq_mcq 279/438, rwq_ff 222/327 = 571  -> 77/1042 = 0.073896
  * RECALL_GEN = {temperature 0, max_tokens 512, seed 42} (study_r1_vllm CELLS K1, SEED). HEADER_TEXT "D2 history".
  * harness SS body (bodies.build_body kind=recall): content = [text "D2 history", image part with client uuid
    <run>|<dev>|<sess>|<qid>|img, text = build_messages template]. Text-before-image header; offline kit put the prompt
    text FIRST then the image, no header, no uuid.
  * harness image: the RAW bytes of <frames_root>/<qid>|img (frames_root = ~/data/live2/frames_by_ref on the H100),
    labelled data:image/jpeg (bodies._data_url). Staging script NOT recoverable from origin (image_settings_by_type.py
    says so); measured prompt tokens match the manifest native dims under the server's mm-processor-kwargs
    {shortest_edge 4096, longest_edge 16777216}, i.e. native resolution, no downscale (SS2 max side 1536, max area
    2.16 Mpx < 16.8 Mpx). Offline kit: same native resolution (MAX_SIDE 2048 never binds) but RE-ENCODED JPEG q90.
    So A-harness and A-offline differ by header, part order, uuid and JPEG re-encode. The runner records sha16,
    format and dims of every image actually sent.
  * the harness pool is the EVAL part only (data_sources.ss2_questions part="eval", 70 percent); the FAIR gap is over
    all 1,042. The runner profiles all 1,042 and summaries also report the eval part separately.
  * harness on-time rule: delivered = first_s (first SSE line, asyncbackend) and under ruling Option 1 the cloud_answer
    leaves at the FIRST CONTENT TOKEN with cloud_letter from the text so far. For a multi-token SS answer format the
    harness would (a) judge the 2 s deadline on TTFT, not completion, and (b) deliver a truncated answer. The runner
    therefore reports both frac_first_line_within_2s and frac_total_within_2s.
  * refspatial: the manifest has no `question`, so the harness sends prompt_text ("Please point out the orange box.")
    and drops `suffix`; confirmed in the dry output. rwq free-form gets "single word or number" plus "Reply with only
    the letter (A-E)".

RUNNER DESIGN
  formats: A = kit prompts exactly (refspatial_prompt, max = manifest 256; realworldqa_prompt, max 16), seed 0 (ss2_run).
           B = refspatial single point (text below, max 24); rwq question verbatim (max 16) == A, seed 0 (offline seed,
               because B is a scored-format variant of the offline kit, not of the harness).
           C = bodies.build_body(kind="recall") exactly as coordinator._submit_recall builds it, seed 42, max 512.
  wraps:   harness (default, all formats) = the committed build_body with header and uuid, raw staged bytes;
           offline = the ss2_run body (text, image) with kit jpeg_data_url, for the A reproduction control.
  sending: ONE REQUEST AT A TIME, stream, temperature 0; ttft_line_s (harness definition, first SSE line),
           ttft_s (kit definition, first content token), total_s, prompt/output tokens, finish_reason.
  caching: prefix caching on; harness wrap = per-question cache_salt and uuid unique to the run tag -> cold single-shot;
           offline wrap = content-keyed mm cache, repeated RefSpatial images warm within the pass, as committed.
  resumable: per-question JSONL appended + flushed; a qid with http 200 is skipped on restart; run meta pins server
           and served model and refuses a resume against a different one.
  scoring: committed scorers imported (refspatial_parse_points + refspatial_point_accuracy + load_binary_mask;
           realworldqa_score). No wrapper logic beyond: correct = score >= 0.5 (the FAIR definition); C refspatial and
           C rwq_ff marked UNSCORABLE (only the harness letter is kept as diag_harness_letter, never counted).
  per-question row: qid, subset, split_part, format, wrap, model, prompt_sent, header_sent, max_tokens, seed,
           body_content_digest, image{bytes, sha16, w, h, file_format}, raw_output, parsed_answer, score{...,correct},
           output_tokens, prompt_tokens, ttft_line_s, ttft_s, total_s, finish_reason, http_status.
  summary per run (<tag>.json, _provenance via stamp): per subset (never averaged) accuracy, k, bootstrap 95 CI
           (seed 7, 2,000 reps, percentile), mean point accuracy, zero-point count, output tokens mean/median/p95,
           decode ms (total - ttft), ttft, single-request e2e, finish=length fraction, frac_total_within_2s,
           frac_first_line_within_2s, and frac_within_2s_at_harness_prefill = mean[ttft_C(q) + decode_F(q) <= 2 s]
           (this format's decode on the harness (C) prefill of the same question, cloud only); eval-part repeat.
  --summarize: cross-run table per format|wrap|subset with cloud, device and the PAIRED cloud-minus-device gap
           (paired bootstrap, seed 7, 2,000); only matched (format, wrap) pairs; refuses a pair whose image sha16
           differs; A<->B rwq fill only when body_content_digest matches; pooled k/n gap reported separately and
           labelled "FAIR-table definition, for comparison with 0.073896 only"; A-offline reproduction control
           (identical raw answers vs results/casestudy/study_ss2/*_{cloud32b,device}.json, committed k listed).
  outputs: results/fidelity/ss2_prompt_profile_2026-11-28/ss2_prompt_profile_<F><wrap>_<qwen3vl32b|qwen3vl4b>_<device>
           {_perquestion.jsonl, _runmeta.json, .json} and ss2_prompt_profile_summary.json. Never writes outside that
           dir; never touches results/casestudy/study_ss2/, oracle_fair_table.json or fair_const.py.
  DESTINATION CONFLICT: the user wrote results/ss2_prompt_profile_2026-11-28/; CLAUDE.md requires results/<purpose>/,
           so the default is results/fidelity/ss2_prompt_profile_2026-11-28/ (purpose fidelity). Also: CLAUDE.md wants an
           E-id row before the run; none exists for this job (open question). Model slugs qwen3vl32b / qwen3vl4b are not
           in the CLAUDE.md slug table (qwen3vl4b is already used by committed SS2 files).

FORMAT B TEXT AND JUSTIFICATION
  refspatial: "Locate {obj} in this image. Reply with only one point, formatted as (x, y), where x and y are integers
  from 0 to 1000 giving the point's position normalized to the image width and height."  max_tokens 24.
  * valid answer type: a point is RefSpatial's own answer type (RoboRefer get_prompt asks for points; "(x, y)" is the
    official summarize_acc text2pts tuple form).
  * scorer-compatible: refspatial_parse_points finds no JSON/bracket pair and falls to the official _TUPLE_RE;
    verified here: "(523, 412)" -> one point, also "[523, 412]" and JSON forms parse. The kit's COORD_MODE norm1000
    (validated on the 9-item smoke for Qwen3-VL) scales it to pixels, so the prompt states 0..1000 explicitly to keep
    the model on its native grid; the 9-item smoke in run_plan.sh step 1 re-checks the convention before the sweep.
  * scoring of one point: refspatial_point_accuracy on a 1-point array = 1.0 if the point is inside the binary mask,
    0.0 if outside or out of bounds; correct = >= 0.5 = point in mask. NOTE the granularity differs from A, where a
    multi-point answer scores the fraction in mask and is correct when at least half the points are inside.
  * cap: "(523, 412)" is about 10 Qwen tokens (digits tokenise singly); 24 leaves room for a short preamble without
    truncating; finish_reason=length is recorded, a truncated reply simply parses fewer points.
  rwq free-form and rwq MCQ: the dataset question verbatim (it already ends "Please answer directly with a single word
  or number." / "...only the letter of the correct option and nothing else."), max 16, scored by realworldqa_score.
  So B == A on RealWorldQA by construction (dry: content digest equal on every rwq question).

TIME ESTIMATE (H100, GPU 2, single requests; from the committed StudySS2 cloud run: refspatial 331 s, rwq 299 s)
  server start (study_live2_pilot.start_server(27.0))          ~8 min (estimate)
  smoke (B 9 + C 3)                                            ~2 min
  A offline control 1,042                                      ~11 min
  A harness 1,042                                              ~11 min
  B harness refspatial 277 (~10 output tokens)                 ~2 min
  C harness 1,042: rwq ~4 min; refspatial ~1 min if it answers a letter, up to 53 min if it runs to 512 tokens
                   (22 ms/token measured in A)                 6 to 58 min
  total cloud                                                  ~40 min typical, ~92 min worst
  optional 4B-on-H100 fallback (server + B + A)                ~15 min
  -> well under 4 h even shared with job 1 unless job 1 needs more than about 2.5 h: no escalation needed.
  Orin (parallel, not H100 time): device B harness 1,042 ~17 min, device A harness refspatial ~10 min, optional
  device A offline control ~22 min.
  PARALLEL: all Orin device passes run while the H100 runs; H100 passes are sequential (single-request latency) and
  never overlap job 1 on GPU 2; summarize is CPU after both.

DEVICE SIDE
  committed device = experiments/casestudy/ss2_run.py --tier device --model qwen3vl4b on the Orin (vLLM 0.20.0,
  :8000, provenance jetson_orin), offline wrap. For B the 4B needs the B prompt: run_plan.sh runs this runner on the
  Orin (--model device, --harness-image-src manifest since the Orin has no live2 staging). If the Orin is unavailable,
  run on the H100 with --device-slug h100nvl, which names the file and provenance (never mixed silently).
  Stack mismatch to state in any comparison: Orin vLLM 0.20.0 4B vs H100 vLLM 0.31.0 32B (input and decoding match).

SS ANSWER-TEXT LOGGING SWITCH (ss_text_log.diff, NOT applied)
  switch: env LIVE2_SS_TEXT_LOG=1 (default off), read at import in coordinator.py and fleet/emulator.py; inherited by
  the procsplit child.
  coordinator: after the request.jsonl row in _collect (where the full response text r["text"] exists, i.e. the
  streamed body assembled by asyncbackend), for kind recall on an asst* device, append one row to
  <run dir>/ss_text.jsonl: request_id, opportunity_id, device_id, session_id, question_id, prompt_format
  ("C:robot_mcq_recall(study_o_q4.build_messages)+header:D2 history+RECALL_GEN"), answer_text, http_status,
  prompt/output tokens, max_tokens, dry_run.
  emulator: just before outcomes.jsonl is written, join ss_text.jsonl by cloud_payload.request_id and add
  ss_answer_text and ss_prompt_format to those SS outcome rows only.
  WHY NOT in cloud_payload: the delivered payload is the FIRST-TOKEN event (Option 1), so text there would be
  truncated, and adding a field to the event would change _comparable / n_forward_mismatch accounting and the wire.
  The join keeps every event, decision, body, count and ordering untouched. run_dir == emulator out_dir in both the
  in-process and the procsplit runner (run_live2_real.py:534/581), so the join finds the file.
  PROOF RUN HERE (dry emulator, no GPU, no HTTP; trace 16 devices ratio 3:11:2, 600 s, ss2 question set, epg, per-frame;
  arms always-cloud-fcfs and covex-v6-fair-final-cand-tl; with and without an injected deterministic dry text):
    determinism   origin OFF vs origin OFF: identical (decision.jsonl after removing the wall-clock field
                  decision_latency_ms, which differs between two identical origin runs; all else byte for byte)
    P1 OFF        origin vs patched, switch OFF: decision, request, residency, outcomes, per-request body digest
                  sequence (body_digest, max_tokens, submit time, order), counts, fairness digests: ALL IDENTICAL;
                  no ss_text.jsonl created
    P2 ON vs OFF  same files identical; outcomes identical after removing ss_* keys; ss_text rows = SS requests
                  submitted (106 / 109), joined into all SS outcomes with a cloud payload (106 / 109), 0 non-SS rows
                  touched, max_tokens 512 in every row
    result: ALL PROOFS PASS (dry_proof.txt). First attempt caught a symlinked tree loading the origin coordinator
    (switch never reached the object: ss_text absent); fixed by a real copy, recorded as the Step 2b check.
  LIVE PROOF PLAN (H100, when enabled): one short live cell ON and OFF cannot be byte-compared (wall timing), so on
  live: (i) per-request wire_sha256_16 of SS bodies identical between an ON and an OFF replay of the same trace is NOT
  expected (timing differs); instead check on the ON cell that ss_text rows == SS completions in request.jsonl, every
  row's max_tokens == 512, answer_text non-empty for every 200, and outcomes rows minus ss_* keys have the same key set
  as an OFF cell; the byte identity is carried by the dry proof above plus the fact that OFF executes no new line.
