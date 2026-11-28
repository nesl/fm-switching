See the D346 entry in research/AUTONOMOUS_LOOP_2026-11-26.md (2026-11-28 08:25). Full notes: scratchpad coordrx/out.txt (copied below).
COORDRX DIAGNOSIS (D346), origin/main 8d41c054 (harness files as at 2926c315 per H100 hashes). CPU-only, read-only.
Scripts: tl.py (request timeline), dl.py (decision timeline), lag.py (wire-time minus decision-time), hc2.py (engine counters).

== EVIDENCE TABLE (committed cells)
cell                         reqrows max_t_submit max_t_done peak_inflight  decisions_max_t  rel_decisions rows  parent_backlog
simplestream n20 s4          5311   485.7        1378.3     2458           963.4            13067       5311     863*
simplestream n20 s4 rep2     6311   487.6        1319.5     2845           958.3            12998        -       2371
mooncake n20 s4              4402   402.1        1306.2     1957           916.9            12339       4402     3848
eco-llm n20 s4               4661   418.7        1208.7     2211           901.4            12208        -       4084
simplestream/mooncake/eco n24 4070/3936/3736  311/300/277  1315/1285/1202  2410/1956/2051  754/765/749   -  10838/7778/107
llf n20 s4 (clean)           6528   1199.7       1199.6     8              1199.6           6528        6528     37
confidence-cascade n24 (clean) 6108 1199.8       1199.0     714            1199.8           6108        6108     43
mooncake n20 c3-11-2 (clean) 8182   1199.6       1199.6     59             1199.6            -           -       49
(* simplestream n20 first cell's coordinator_result is STALE, see F5)

F1  Submissions do NOT stop. Release decisions continue at the steady 820-870/min (n20) / 1030-1090/min (n24) until event
    time 750-963 s (dl.py); only request ROWS stop. Rows are written at completion (_collect, coordinator.py:2261ff) or as
    abandoned at finish (procsplit.py:509-510). The last logged requests have durations 825-1023 s and end at 1202-1378 s:
    t_submit + latency = the moment the child was killed. "Last submission 277-488 s" is a survivorship horizon, and it is
    earlier at n24 because latency grows faster. 7,756 (simplestream) / 8,402 (mooncake) release decisions have no row.
F2  The cloud is genuinely overloaded by these arms (an experiment property, not a bug): ~13.8 req/s offered (n20) vs ~5-6
    req/s served (llf-like engine throughput, which the engine counters keep up through ~1450 s: hc2.py). TTFT p50 grows
    3 s -> 86 s -> 166 s -> 298 s -> 561 s by minute 0..5. Engine alive the whole time (gen/prompt counters advancing).
F3  From minute ~4 the CHILD is saturated: (a) first-token-to-stream-end for 2-token answers goes 1.5 s -> 50 s -> 187 s
    -> 227-283 s (client not reading its streams); (b) wire minus decision time grows 0.01 s -> 3-12 s (simplestream) / 25-29 s
    (mooncake) by minute 6-8 (clean cells: 0.03 s max 0.4); (c) the parent's send backlog to the child reaches 863-10,838
    messages (clean 37-49) = the child's rx thread is not draining the socket; (d) late in the run the engine idles in 30-100 s
    stretches (hc2.py zeros) while thousands of requests are open: the queue has moved INTO the client.
F4  Candidate GIL hog (code): Live2Coordinator._collect walks ALL in-flight futures (coordinator.py:2263, fut.done() takes the
    Future's condition lock) and rebuilds the list (2413); it is called on every parent event and tick (bridge.py:62,73) and on
    every 5 ms self-tick (procsplit.py:486-489). At 2,000-7,000 in-flight that is ~0.25-0.7 core-seconds per second of pure
    Python in the decision thread (estimate, ~0.5 us/future), growing with the backlog: a positive feedback loop. Clean
    cells already run the child at 37-50 % of a core with <=714 in-flight. NOT PROVEN: the py-spy --gil profile decides.
F5  STALE RUN DIR: simplestream_n20_s4_..._L3_epg_rq30 raw dir was reused. Its coordinator_result.json is from another attempt
    (pid 2571456, wall_s 386.5, n_decisions 3794, n_requests 5017; this run's engine pid 3479314) and its host_counters_d211.log
    holds two segments ~61,000 s apart (39 + 154 samples). The runner (run_live2_real.py:592-594) read that file and labelled
    the cell parent_closed_before_result with n_requests 5017 / n_errors 6 (this run's rows show 29 ReadErrors). The driver's
    `mkdir -p $d` (v48:364) never clears $d. The decision_time sidecar the H100 saw (32,693 B) is likely the stale one too.
F6  The signature is wider than reported: mooncake n32 s4 c3-11-2 (both reps: child_never_sent_result and parent_closed with
    child wall 1400.9 s, backlog 866/1486) and mooncake n16 s4 out-k3-d120 (parent_closed, child wall 1379.6 s, backlog 1184)
    carry the same rx ConnectionResetError. Those are the near-miss form: the child finished just after the 180 s drain.

== RANKING
1. ROOT (supported, mechanism of slowness unproven): offered load >> engine capacity for cloud-first baselines -> unbounded
   in-flight -> child CPU/GIL saturation (leading candidate F4) -> child lags its own clock and stops reading its socket and its
   HTTP streams -> at finish the 'finish' message sits behind a backlog of hundreds of seconds of events.
2. H1 (CONFIRMED as the crash mechanism, a consequence): RemoteCoordinator.close (procsplit.py:217-239) waits drain_close_s=180
   then sock.close() with unread replies in its buffer -> Linux AF_UNIX gives the peer ECONNRESET -> child rx thread dies
   (procsplit.py:390 -> 94 -> 86) without putting None in the inbox -> SplitRun.__exit__ join(60) then terminate()
   (procsplit.py:593-596) kills the child before finish: no coordinator_result.json (child_never_sent_result, run_live2_real.py:596),
   no abandoned rows (REQUEST_LOG_INCOMPLETE, run_live2_real.py:649-652). wall 1534-1573 s = start-up + 1200 + emulator drain +
   180 + 60 fits. parent_closed_before_result (594) = child wrote its file but after the parent closed; child_never_sent_result
   = no file at all.
3. H3 (arm-specific deadlock): REFUTED. Decision thread alive and deciding at full rate; the arms that crash share only the
   property "release every opportunity to the cloud, no in-flight cap" (llf peak 8 in-flight; cascade 714 and survived).
4. H2 (a limit at ~5-6 k requests / ~486 s): REFUTED. submit_live2 is non-blocking (asyncbackend.py:131-132), no semaphore or
   in-flight cap; httpx max_connections 16384 (asyncbackend.py:105-107) is never reached; no PoolTimeout/ReadTimeout/EMFILE;
   ulimit -n 1,048,576; the stop time varies 277-488 s and tracks latency growth, not a count. ReadError('') rows (9-29) are
   server-side stream closes under overload (one also in clean cascade n24 and mooncake c3-11-2); they do not gate submission.
   The H100 reading "submission path blocks / engine stalls" is contradicted by F1 and the engine counters.
5. H4 (OOM/signal): unnecessary; the child dies by the parent's terminate() (SIGTERM). H100 can confirm: child exitcode -15
   (not logged; the DIAG records it via py-spy/stdout), no OOM line in dmesg.

== DIAG RECIPE: scratchpad/coordrx/diag_coordrx.sh  (GPU 2 only, only when the driver is idle; tag _DIAG; never scored)
   bash diag_coordrx.sh mooncake 20 720     (fallback if no crash: mooncake 24 600; control: llf 20 720)
   argv = the v48 cell() line for tag _L3_epg_rq30 with SS_POOL_ARGS/EPG_ARGS/RQ30_ARGS expanded, --run-s 720, fresh --out.
   Instruments (no harness edit): py-spy record --subprocesses --gil --nonblocking (GIL-holder stacks of the child; py-spy is an
   ancestor so ptrace_scope 1 is fine); every 5 s: parent/child fds, child RSS, per-TID CPU of the child (top thread ~100 % =
   GIL holder), established TCP to :8031 (client in-flight), unix-socket Recv-Q of child and parent (rx starvation), vLLM
   num_requests_running / waiting / generation_tokens_total, /health, decision.jsonl rows + last t (child lag vs wall),
   request.jsonl rows + last t_submit.
   Decisive read-outs: (i) share of GIL samples inside _collect / Future.done (F4 true if dominant from ~minute 4);
   (ii) http_estab >> running+waiting late in the run = backlog in the client; (iii) dec_last_t falling behind wall.
   720 s chosen because the lag is ~25 s at minute 6-8 and ~470 s at the kill in the 1200 s cell; a crash at 720 s is likely but
   not certain. The instrumentation, not the crash, is the test.

== FIX (staged, NOT applied): scratchpad/coordrx/fix.diff
   coordinator.py: each real future gets add_done_callback setting a dirty flag; _collect skips its walk when nothing completed
   since the last walk (prune of _released_prefills still runs every call; dry runs and backends without callbacks keep the
   full walk). A walk that would find nothing done leaves futures unchanged and settles nothing, so no decision changes; the
   only difference is CPU (and the scheduling jitter of when a completion is noticed, which was already racy).
   run_live2_real.py: a coordinator_result.json already in the run dir is renamed .stale_<mtime>.json before launch (F5).
   NOT in the diff (behaviour or driver): request timeouts, backlog cap, admission change; raising drain_close_s (would only hide
   lag); driver v48 refusing a non-empty $d (recommended, driver not harness plumbing).
   CAVEAT: if py-spy shows the GIL is held elsewhere (body build on the loop, SSE parsing), this diff is not the fix; stop.
   CAVEAT 2: the fix removes a client-side latency inflation, so the saturated baseline cells' SCORES will change (F3 shows
   their late answers were delayed by the client). Every crashed or near-miss cell (F6) carries harness-inflated latency.

== PROOF PLAN
(a) diag_coordrx.sh with the patched tree, same argv: result_status received, request_log_complete true, child top-TID CPU
    < ~80 %, parent backlog < 100, wire-minus-decision p99 < 0.5 s throughout, 2-token first-token-to-end stays near 1.5 s.
(b) rerun mooncake_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30 (clean, received, peak 59 in-flight) tagged _FIXPROOF; compare to
    its committed cell: robot standing_accuracy 0.392226, robot on-time 0.187279, dashcam AP@0/0.5/1/1.5, assistive on-time
    0.890295, n_requests 8182, n_errors 1, decision counts by kind. Noise floor from the committed pair covex-v6-fair-final n16
    s4 vs _rep2: robot acc 0.6288 vs 0.6439 (0.015), robot on-time 0.9545 vs 0.9621 (0.008), AP@0 0.0223 vs 0.0250 (0.0027),
    AP@1 0.0101 vs 0.0108 (0.0007), assistive on-time equal, n_requests 12193 vs 12177 (0.13 %). Pass = every delta within
    about that floor. (A dry-run digest proof says nothing: the fast path is off in dry runs.)
(c) mooncake_n20_s4_1200s_h27_3t_L3_epg_rq30 tagged _FIXPROOF in a FRESH dir: received, request_log_complete, rows = submitted,
    abandoned rows present for the queue still open at finish; its scores are expected to differ from the crashed cell.
