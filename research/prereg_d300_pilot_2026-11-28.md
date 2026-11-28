# Pre-registration: d300 s4 pilot (user ruling D347), written 2026-11-28 before any d300 cell runs

Pilot purpose: confirm the regime is EXERCISED, not a verdict on S2.
Exercised if, in [R+10, R+120] on interrupted-session robot questions:
(i) cand-tl shows cold or late cloud asks attributable to the backlog (report cache path, cached fraction, prompt tokens, TTFT, on-time, correct, per ask), and
(ii) F0 releases catch-up work (S2 counters: evaluations, released, held, windows opened/closed with reason) before at least some of those asks.

Design (fixed by the user; reported, not changed): n20, `_c3-11-2` mix, k = 14 (all robots, correlated), 13.6 Mbps, 1x memory, buffered semantics, 1200 s, the same arms' tags as the d188 network block (COVEX arms with `_qp`); d = 300 s (Li et al., SIGCOMM 2021 anchor: over 80% of data stalls under 300 s); backlog about 13.5k tokens per victim; per-seed t0 by an evidence-placement search over t0 on the dataset's real question times (no synthetic questions). Dev seeds only (s4 to s6); never seeds 1 to 3. Cells: cand-tl and F0 (cand-tl-sync) at n20 s4 with the Step 1 t0, d300, `_link`, `_qp`; control: the existing cand-tl n20 s4 no-outage `_qp` cell (shared by both).

Step 1 (CPU) stop rule: STOP AND REPORT if any seed has Q < 15 (victim robot questions in [R+10, R+120] in interrupted sessions) or over-limit asks (history at ask + backlog + question > 32,768 tokens) cannot be avoided; that triggers the synthetic-question fallback, which is the user's call.

Ordering on the H100: the D346 crash fix first (pushed and verified), then this pilot, then D345 SS profiling. STOP after the pilot and report; the matrix is not queued; the user decides from the pilot.
