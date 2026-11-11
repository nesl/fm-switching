# StudyE9-episodes — mechanism verification (CLAUDE.md Steps 1–5)

**Recorded 2026-11-11, BEFORE the sweep ran.** The values below come from probe runs made only to
instantiate the links (threshold fitting, delay arithmetic, and four escalation cells), not from the
sweep. Offline analysis of committed StudyD14 score traces; CPU only; no GPU, no server, no
inference. Every score is the continuous log P(Yes); no literal Yes/No answer is used anywhere.

## Step 1 — the causal chain

A device that must decide every second whether to call the cloud is making FORMULATION's placement
decision `p_i` online (§Decisions), under §Constraints 2 (*serving feasibility*: the serving node
must answer within the latency SLO) and §Objective (maximise the fraction of requests meeting the
SLO, with cloud work reported as an explanatory cost, not folded into the objective). The chain the
experiment tests is:

**StudyE5 Part G measured that 32B separates the seconds just before a crash from normal driving
better than 4B at a fixed horizon (AP 0.147 vs 0.102 at h = 0, CI excluding 0 up to h = 1 s).** If
that is true, then inside an escalation episode a 32B resolver reaches its alarm threshold or its
dismiss threshold *sooner* than a 4B resolver whose thresholds are set at the same per-second
false-alarm rate on negatives. Sooner resolution means fewer resolver invocations per episode; and
because a wrong dismissal on a positive clip sends the device back to monitoring and a later trigger
re-opens an episode, better resolution also means fewer re-escalations. Both reduce total cloud work
per clip-hour at the same trigger rate and the same alarm false-alarm rate. Separately, the score
stream the application sees (resolver inside episodes, device outside) should keep more of
always-cloud's AP the more often the resolver is running — which is the predictive-quality side of
the same trade.

**A property of the design that bounds the effect, stated before the sweep:** `tau_alarm` and
`tau_dismiss` are fitted as quantiles of *each model's own* score distribution on training-fold
negative seconds. By construction, therefore, both resolvers alarm on the same fraction of negative
seconds and fall below their dismiss threshold on the same fraction of negative seconds. Any
capability effect on episode length must come from the *ordering* of seconds within a clip and from
positive clips, not from a level difference. This caps how large the effect can be and is carried
into Step 5.

## Step 2 — instantiate each link

| causal link | implementing quantity | value / range in the probe | varies as expected? | evidence |
|---|---|---|---|---|
| the device opens episodes at a controllable rate | `tau_trig`, device 4B N1 quantiles on training negatives | −2.579 / −4.511 / −7.001 / −10.750 at trigger rates 5 / 10 / 20 / 40 % | yes, monotone and it is the load knob | fitted thresholds |
| thresholds are matched across models | `tau_alarm` at 1 / 5 / 10 % FAR | 4B N1 −0.299 / −2.579 / −4.511; 32B N1 −0.693 / −4.883 / −7.963; 32B N3 −0.445 / −4.635 / −7.126; 32B N9 −1.655 / −6.608 / −9.000 | yes, each model on its own scale at the same negative-second rate | fitted thresholds |
| each fold has enough data to fit | training negative seconds per fold | 2,578 (of 5,196) | yes | fitted thresholds |
| resolver capability changes episode resolution | episodes ending in `dismiss` on positive clips, 32B N1 vs 4B N1, zero latency, trigger 10 %, FAR 5 % | **134 vs 81**; `alarm` 341 vs 376; `cap` 10 vs 20 | yes — 32B resolves by dismissal more often and 4B runs to the cap twice as often | probe |
| resolution time → cloud work | resolver invocations per positive clip-hour, same cell | **766.9 (32B) vs 856.5 (4B)**; negatives 604.2 vs 620.1 | yes, and in the direction the chain predicts | probe |
| re-escalation after a wrong dismissal | episodes per clip | 503 vs 504 episodes on 150 positive clips at trigger 10 %; 818 vs 668 at trigger 20 % | yes, and it is not monotone in the model — reported, not assumed | probe |
| latency consumes the episode | `d_cloud` in whole seconds | zero setting 0 everywhere; measured 1 (32B N1, both loads), 1–2 (N3), **3 (N9 @25 %) and 4 (N9 @75 %)** against `L_max` = 10 | yes, strongly at N = 9 | delay arithmetic from StudyD4 / D7 / D7b / D8 |
| latency changes cloud work | invocations per positive clip-hour, 32B N1, trigger 10 %, FAR 5 % | 766.9 (zero) → 852.6 (measured @25 %) | yes | probe |

**No link is ABSENT or CONSTANT.** The weakest is re-escalation, whose direction is not fixed by the
chain; it is reported as measured.

## Step 3 — trace one unit

The runner writes one instrumented episode trace to `e9_results.json → trace_example`: a positive
clip, chosen as the first one that contains both a false dismissal before the event and a
re-escalation. It records, per second: the wall second, the second relative to the event, which
frame-second the device score came from, which frame-second the resolver score came from, the score
the application stream carries and its source, and whether an episode was open — together with the
three fitted thresholds, `k`, `L_max`, the cooldown, every episode's open/close second and outcome,
the invocation count and the GPU-seconds. The arithmetic is checkable by hand from those columns.

## Step 4 — negative controls

- **(a) Swap the resolver.** Running escalation-32B's code path with 4B N1 resolver scores, 4B N1
  thresholds and 4B N1 cloud latency must reproduce escalation-4B exactly, cell for cell. This tests
  the implementation, not the data: if it fails, the two arms differ by something other than the
  resolver.
- **(b) Shuffle the resolver scores across seconds within each clip.** The resolver then carries the
  same marginal distribution but no timing information, so AP at h ≤ 1 s must fall toward the base
  rate (0.0281). If it does not, the alarm timing is not coming from the resolver's within-clip
  signal.

Both are pre-registered and are run on the primary configuration.

## Step 5 — alternative explanations

1. **"32B shortens episodes because it is better" vs "32B shortens episodes because its score
   distribution has a different shape."** The thresholds are matched on negative-second rates, which
   equalises the *level* but not the *shape* (skew, within-clip autocorrelation). The two are
   separated by negative control (b): shuffling destroys within-clip ordering while preserving the
   marginal distribution, so whatever survives the shuffle is shape, not timing.
2. **"Escalation keeps AP because the resolver is good" vs "escalation keeps AP because the device
   score alone already carries it."** Separated by the escalation-4B arm, whose resolver *is* the
   device model: any AP that escalation-32B has over escalation-4B at the same trigger rate is the
   resolver's.
3. **"Cloud work falls because episodes are shorter" vs "cloud work falls because fewer episodes
   open."** The trigger threshold is fitted on the device arm only and is identical across the two
   escalation arms at a given trigger rate, so the number of *opening* triggers is the same input;
   episodes per clip and invocations per episode are reported separately so the two cannot be
   confused.
4. **Latency as a confounder.** A longer `d_cloud` both delays the first usable resolver result and
   wastes invocations issued before it arrives. N = 9 at 75 % load has `d_cloud` = 4 s against
   `L_max` = 10 s, so at most 7 of its 10 charged invocations can influence the outcome. Both latency
   settings are reported for every cell, and the zero setting is labelled as pure capability.
5. **The matched-rate construction itself.** As stated in Step 1, matching thresholds on negative
   seconds means negative-clip episode behaviour is equalised by design. If the measured capability
   effect turns out to live almost entirely on positive clips, that is the expected consequence of
   the design and not evidence of a larger effect; the report splits positives and negatives for
   exactly this reason.
