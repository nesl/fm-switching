# StudyOUTAGE-HEADROOM — can the reconnect burst let recovery ORDER change on-time answers?

PRE-REGISTERED 2026-11-24, PRELIMINARY (no cells, no new runs). Owner: Orin, offline from the
committed s4 trace and the D162 cost model. This file is the formulation and the upper-bound
argument; the computed values land in `reports/figures/outage_headroom_results.json` and
`reports/study_outage_headroom_results.md` and must not be written until this formulation is
committed. DO NOT PLOT.

## The question
After a network outage, the offline devices buffer work and deliver a burst at reconnect. If that
burst is large enough that the ORDER in which recovery is processed (FIFO replay of the backlog vs
an ideal deadline-first order) changes the number of on-time CORRECT cloud answers, then an outage
is a regime that can SEPARATE policies. If the backlog clears in under the shortest deadline, the
order cannot matter and an outage cannot separate policies. This is a headroom (necessary-condition)
study: it bounds the MOST that ordering could ever save; it does not claim any policy achieves it.

## What would invalidate this run (Step 0, before any value is computed)
- **The trace must be the committed one.** Regenerate s4 with the args already validated by the
  fairness digest and re-assert the digest BEFORE using any record; a mismatch stops the run.
      generate_trace(seed=4, n_devices=16, ratio="40:40:20", run_s=1200.0, mode="A",
                     robot_question_set="lh_req", ss_question_set="ss2", dashcam_format="epg",
                     robot_upload="per-frame", robot_reask_mean_s=30.0)
  committed trace_fairness_digest = 96c1a0b486381709e2fc63e9b0f33f9e1ba1d887d6cedf21d89d407621177849.
- **The cost model must be D162, not the gated-out per-request model.** GPU time uses
  first_token_s = 0.0678 + 0.000182 * uncached_prefill + 0.000154 * uncached_queued_ahead (the
  model that passed its D168 gate), NEVER cost_model_gate.json's per_overlap 0.0380 s/request.
- **The window must be the right register.** The recovery window is bounded by CLOCK time at the
  link and the GPU, not by token counts alone; a decision already past its deadline at reconnect is
  LOST to every ordering and is excluded from headroom, not counted as saved.
- **Upload needs bytes, not tokens.** Upload time at the uplink is image BYTES / rate; the token
  law (below) sizes PREFILL, a separate resource. The two are not interchangeable and are kept on
  separate budgets. If the committed per-frame byte size is unavailable, the run STOPS and reports
  that gap rather than substituting tokens for bytes.
- **Is this preliminary bound even reachable?** If every scenario clears in under 1 s the headroom
  is structurally zero and the answer is "outages cannot separate policies"; that is a valid
  result, not a null to explain away.

## Causal chain (the mechanism this study bounds)
If an outage of length D buffers W tokens of prefill and B bytes of upload on the offline devices
(FORMULATION.md: Context Inertia has a physical transfer+reconstruction component that grows with
context length), then at reconnect the GPU and the uplink are occupied clearing that backlog for a
RECOVERY WINDOW of length R; fresh deadline-bearing decisions from ALL devices that arrive inside
[reconnect, reconnect+R] must wait behind the backlog under FIFO; a deadline-first order can serve
those fresh decisions before the stale backlog and rebuild only the histories whose question falls
in the window; the DIFFERENCE in on-time correct answers between the two orders is the headroom.
The link is "maintenance cost -> occupied recovery window -> admission/timing of in-window
decisions". If R < min deadline the window contains no flippable decision and the link is ABSENT by
construction (reported as the no-room verdict, not as a measured null).

## Fixed inputs (committed artifacts only; no reruns)
- Token law (D2 / EPG): prefill tokens for a dashcam/robot frame set = EPG_TEXT_TOKENS(42) +
  EPG_TOK_PER_FRAME(338) * n_frames; decode = 2 (an MCQ letter). "338 per frame plus the header."
- Deadlines (the cell sweep): L_dash = 1.0 s, L_rob = 3.0 s, L_ss = 2.0 s. A decision is on-time if
  delivered by arrival + L_type - net, net = RTT/2 at the committed link.
- Link (D75): uplink 13.6 Mbit/s, RTT 44 ms. ALSO a LOW tier, value stated and marked PROVISIONAL
  until the Ookla tiers land; the low-tier number is reported beside the default, never in place of
  it.
- Peak prefill rate (D230 (12)): T(1x) = 17,945.2 tok/s; decode charged at the same T (understates
  decode time, so it keeps the recovery window a LOWER bound on clear time only where that direction
  is argued; see the bound direction note below). This study is 1x only unless extended.
- Device composition and per-type frame cadence are READ FROM THE REGENERATED TRACE at compute time
  (robot `robo*`, single-shot `asst*`, dashcam the monitor devices); no device count is written
  into this pre-registration.

## Scenarios
- Outage length D in {30 s (primary), 10 s, 60 s (shape)}.
- Offline sets: {one robot device}, {one dashcam device}, and correlated K in {2, 4, 7} devices
  offline together. The K-device sets are drawn in a fixed, recorded order from the trace's device
  list (type-balanced where K allows; the exact membership echoed in the output).
- Start times: 5 evenly spaced instants t_k = run_s * k / 6 for k = 1..5 (200, 400, 600, 800,
  1000 s), each outage fully inside the 1200 s run for every D.
- Grid = {3 lengths} x {robot, dashcam, K2, K4, K7} x {5 starts}; every scenario reported, none
  aggregated away.

## Per scenario, computed
1. **Backlog at reconnect**, per device type:
   - buffered frames = the frames/instants the offline device(s) would have uploaded during
     [t0, t0+D], read from the trace (dashcam decision instants and their cumulative EPG frames;
     robot per-frame uploads and re-ask history under robot_reask_mean_s = 30 s);
   - prefill tokens to rebuild them COLD = header + 338 * (uncached frames), robot histories
     rebuilt from empty (no warm prefix survives the outage);
   - upload bytes = buffered frames * committed per-frame byte size.
2. **Upload time** = 8 * upload_bytes / rate, at 13.6 Mbit/s and at the provisional low tier.
3. **GPU rebuild time** = D162 first_token_s evaluated on the cold uncached prefill (with the
   in-window queued-ahead term), summed over the backlog, cross-checked against backlog_tokens / T.
4. **Recovery window R** = reconnect -> backlog cleared, on whichever of {uplink, GPU} is the
   binding resource (both reported; R = max of the two serialized chains, stated explicitly).
5. **In-window decisions** = robot questions, dashcam alert instants and single-shot questions from
   ALL devices (including those that stayed online) whose deadline falls in [reconnect,
   reconnect+R].

## Headroom (the upper bound) and its validity
Headroom per type = an UPPER bound on the on-time cloud answers an ideal deadline-first ordering
saves over FIFO inside the window, in D192 units (dashcam = one alert EPISODE judged over its
instants, recall = one question, single-shot = one question):
- FIFO replays the backlog first, so every in-window decision whose deadline precedes the backlog
  clear time is LATE under FIFO (device answer stands);
- ideal ordering serves deadline work first and rebuilds only the histories whose question is
  in-window, so it can save at most those same decisions, and only the ones that still FIT before
  their deadline at rate T;
- headroom_upper = count of in-window decisions with deadline before the FIFO clear time that fit
  under ideal ordering at T. This is an upper bound because (R1) it credits ideal ordering with
  serving every fittable in-window decision and FIFO with serving none of them, (R2) work uses the
  minimum cold-rebuild tokens, (R3) rate T is the highest measured, (R4) capacity is flat and
  preemptible. Each step only enlarges the saved set, so the true separable gain is no larger.
- Negative or zero headroom is reported as zero (ordering cannot save work that does not exist).

Bound direction note: T high and decode-at-T make the clear time a LOWER bound on the real recovery
window, so the in-window decision set is a SUBSET of the real one -- this keeps headroom an upper
bound on the SEPARABLE gain only together with the fit test; where the two directions would
conflict, the more conservative (smaller headroom) choice is taken and recorded.

## Verdict per scenario
- R < 1 s: NO ROOM (backlog clears within the shortest deadline; order cannot change any answer).
- 1 s <= R <= 10 s: SOME ROOM.
- R > 10 s: LARGE ROOM.
Report per scenario which bucket it falls in and the per-type headroom; conclude which scenarios (if
any) have room, i.e. whether an outage can separate policies at all on this trace.

## Positive control and stop gate
- Positive control: a zero-length outage (D = 0) must give empty backlog, R = 0, headroom 0 for
  every type; if it does not, the pipeline is broken, not the finding.
- Stop gate: if any scenario's headroom exceeds the total in-window decisions of that type, or any
  recovery window is negative, the bound is not a bound -> STOP and report. If the committed
  per-frame byte size cannot be located, STOP (do not substitute tokens for bytes).

## Claim linkage
Bears on FORMULATION.md Context Inertia (physical transfer+reconstruction component) and on whether
a timing/placement policy can be separated from a decomposed one under a transient-capacity regime
(the simulator gate in CLAUDE.md Project overview). A no-room result across all scenarios WEAKENS
the case that outages are a discriminating regime; a room result identifies where to look. It does
not by itself support any policy; it only bounds the opportunity.
