# D201 part 1: what each baseline's published method reads, and every other consumer of a constant

StudyEXIT-EP section 6 found it; D201 ordered the fix. This file is the ANALYSIS half: the
per-baseline method statement taken from each card (item a) and the tree audit (item d). The
plumbing, the decision-log diff and the rerun list are separate commits.

Read at origin/main `56398c852a4bf998eab4a273b8b34d840d310720`. Every line number below is at that
sha. The checked-out tree at `/tmp/claude-1001/mapwt` is about 1,220 commits behind and its line
numbers do not match; nothing here was read from it.

NOTHING HERE IS A MEASUREMENT. One number is measured, and it is labelled where it appears: the
census of what values reach the two arms on one dry s4 cell.

---

## 0. The defect, restated with its line numbers at this sha

`EpisodicStream.delivered_scores` (`baselines/interface.py:100`) is read for its VALUES on the
decision path. Both coordinator writers fill it with a literal `0.0`:

* `live2/coordinator.py:663`, in `_device_answer`, whose docstring at `:655-657` states the
  placeholder deliberately: *"The SCORES here are placeholders: task value is scored offline from
  the recordings (D85, D87), never in this process."*
* `live2/coordinator.py:1917`, the cloud-settle path, which appends the cloud upgrade.

That reading of D85/D87 is right about TASK VALUE and wrong about the DECISION INPUT, which is what
these arms consume.

**THE ZERO IS NOT NEUTRAL, AND THIS IS THE MOST IMPORTANT FACT IN THIS FILE.** The score is
`log P(Yes)` (`baselines/devsplit.py:34-35`; `live2/scores.py:9-12` cites StudyD3
`d3_infer_vllm.py:96-102` and StudyCTRL1c `ctrl1c_calibrate.py:276-277, 298` for the same
definition). Its range is therefore `(-inf, 0]`, and **0.0 is the MAXIMUM of the range**:
`P(Yes) = 1.0`, maximally alarming. Every threshold of the form `v >= tau` where `tau` is a
quantile of observed negatives is satisfied unconditionally. So the affected arms do not fail
silent. They escalate on every instant, and a reader looking for an obviously broken column would
not have found one.

The measured corroboration is in the committed pre-screen itself
(`results/orchestration/live2/frozen_test/baseline_prescreen.json`, seed 4, 16 devices, 1200 s,
40:40:20, lh_req, ss2, dry): `inar-vl`, `routellm` and `always-cloud-fcfs` all land on decision
digest `d2f69d4eb94625b4` with 13,570 decisions. Two score-reading arms are byte-identical to
always-cloud because, fed the maximum of the range, they always escalate.

---

## 1. Item (a): the per-baseline method statement, from the card

### INAR-VL (`inar-vl`, `baselines/inarvl_adapted.py`, card `cards/inarvl.md`)

**WHICH SCORE: the DEVICE's own score, and never the cloud's.** The card's mapping table makes the
substitution explicit: *"image signals | the DEVICE's own delivered score-trajectory statistics |
**ADAPTATION A1 - the largest departure**"*, and A1 says the signals exist in the paper *"to decide
when the edge model is out of its depth"*. The paper's four image signals (blur, exposure, artifact,
detail) are computed from the (image, question) pair; the adaptation replaces them with statistics
of the device's trajectory because re-reading pixels would be new measurement.

**WHEN: every decision period, on the whole visible trajectory, before any cloud answer exists for
the instant being decided.** `decide()` (`:76`) calls `_image_signals(s)` (`:64`) for each stream on
every epoch; the statistics are the last value, the standard deviation (twice) and the maximum
(`:69-72`).

**The recall branch reads NO score.** `:97` passes four hard-coded image signals
`dict(blur=0.0, exposure=0.5, artifact=0.0, detail=0.5)`.

**EXPRESSIBLE LIVE: YES, and no new measurement is needed.** The device's committed per-instant
score already exists for every monitor instant of every generated trace:
`fleet/data_sources.orin_dense_scores()` (`:752`) is StudyORIN1's dense `(file_name, t) ->
{score, p_yes, ttft_s, total_s}`, 42,014 rows on the 0.25 s grid, and `fleet/trace.py:536-555`
already looks each instant up and writes `device_score` into `device_answers.jsonl`, RAISING
(`:538-541`) if the committed set does not cover an instant. The number was on disk beside the
trace all along and the run-time path never read it.

### Hybrid LLM (`hybrid-llm`, `baselines/hybrid_llm_adapted.py`, card `cards/hybrid_llm.md`)

**WHICH SCORE: the DEVICE's own score, and it is FORBIDDEN the cloud's.** The card maps
*"features x | StudyD3 development-split device-trajectory features | ADAPTATION A4"* and A4 says
the features are *"trajectory statistics over the offsets <= the decision moment - strictly causal,
development split only"*. The router emits `p_w(x) ~ Pr[H(x) >= 0]` with `H(x) = q(S(x)) - q(L(x))`
and routes BEFORE either model answers (paper section 3), so it may not see `q(L)`. The card's
amendment 2 item 3b already settled this once, for the recall path: *"the paper's router reads the
QUERY and routes BEFORE either model answers, so it may not read `device_answer_confidence`"*; that
read was reverted and `reads_device_answer` stays False.

**WHEN: every decision period, per stream, before either model answers.** `decide()` (`:71`) calls
`_features(s)` (`:36`), the six `devsplit.FEATURES`: last value, and the mean, maximum, slope,
standard deviation and length of the prefix.

**The recall branch reads NO score** (`:86`, `DEFAULTS["recall_decision"]`), and the card states
that the routing claim is made for episodic streams only.

**EXPRESSIBLE LIVE: YES**, from the same committed table.

**A SECOND FAULT ON THIS ARM, BEYOND THE CONSTANT.** `delivered_scores` is the APPLICATION-VISIBLE
stream: `coordinator.py:1917` appends the CLOUD's answer on top of the device's whenever one
arrives in time (`cstate.py:11` says so). So once real values flow through that channel, this arm
would be reading `q(L)` for every instant the cloud served, which its published method forbids. The
constant hid this: the two writers wrote the same number, so the channel's composition did not
matter. Fixing only the values would leave the arm wrong for a different reason, and that is why
the plumbing commit gives the device score its own channel rather than filling this one.

### Neither arm depends on the cloud score, so the dry cell is a valid proof for both

Stated because the brief requires it: a DRY cell carries no cloud score at all
(`coordinator.py:1853-1857`, and `d192_exit_trigger_probe.py` censused it as None 10,886 times out
of 10,886). If either arm's decisions depended on the cloud score, a dry null would say nothing
about it and only a LIVE cell could prove it. Per the two cards above, NEITHER DOES: both read
`q(S)` only, and hybrid-llm is positively forbidden `q(L)`. The dry s4 cell is therefore the right
proof for these two. It is NOT the right proof for `confidence-cascade`, `cascade-routing`,
`r3-streaming`, `streamscout` or `thinking-qwenvl-atdm`, whose published mechanisms wait for an
answer (`fleet/data_sources.py:245-247`); their proofs need the live cell.

### A third consumer, named by the D200 session, confirmed as the same defect

`baselines/thinking_qwenvl_adapted.py:84-88`. `v = s.latest_score()` then
`conf = 0.0 if v is None else max(min((v + 12.0) / 12.0, 1.0), 0.0)`. With `v = 0.0` this is
`conf = 1.0`, a constant and the maximum of the range, handed to `atdm(rho, conf, ...)` as the
device's confidence. **SAME DEFECT, and it is one of seven, not one of three** (see item d, hit 1).

---

## 2. Item (d): every other consumer of a placeholder, stub or unfed value

Confirmed by reading BOTH the write and the read at this sha. Hits are ordered by whether the value
reaches a policy decision. The "documented?" column matters more than the count: this project
already knows about several of these and says so in the code.

### Tier 1: reaches a policy decision

**1. `delivered_scores` has SEVEN value readers, not the two D201 names, and FOUR writers of 0.0,
not two.**

| read site | how |
|---|---|
| `baselines/inarvl_adapted.py:65` | direct (named in D201) |
| `baselines/hybrid_llm_adapted.py:37` | direct (named in D201) |
| `baselines/constructed.py:110` | via `interface.py:107-108 latest_score()` - **this is B4, OUR OWN constructed arm, not a published baseline** |
| `baselines/cascade_adapted.py:130` | via `latest_score()` |
| `baselines/thinking_qwenvl_adapted.py:84` | via `latest_score()` |
| `baselines/uniscale_adapted.py:59` | via `latest_score()` |
| `baselines/r3streaming_adapted.py:103` | via `latest_score()` |

Writers of the literal `0.0`: `live2/coordinator.py:663`, `live2/coordinator.py:1917`,
**`live/adapter.py:419`** (device branch) and **`live/adapter.py:450`** (cloud branch). The v1 live
adapter is an independent second instance of the same defect.

What each read then computes, traced:

* `cascade_adapted.py:136` `escalate = (v is not None and v >= self.tau_trigger and ...)`, with
  `tau_trigger` the 0.80 quantile of negative `log P(Yes)` (`:74-77`), strictly < 0. At `v = 0.0`
  **every stream escalates on every epoch**. `constructed.py:111-112` is the same arithmetic with
  `self.tau` built identically at `:91`.
* `thinking_qwenvl_adapted.py:87` -> `conf = 1.0` constant.
* `uniscale_adapted.py:61-63` -> context vector `[1.0, 0.0, 0.0, gpu_kv_fraction]`, so the LinUCB
  bandit runs on a near-constant context.
* `r3streaming_adapted.py:103` `abs(v or -12.0)**-1 if v else 0.0`: **0.0 is falsy**, so every
  stream's difficulty is 0.0.
* `hybrid_llm_adapted.py:37-45`, and `routellm_adapted.py:94` which imports the same `_features`
  (`routellm_adapted.py:32`): five of the six router features collapse to 0.0 and **only `len(h)`
  varies**, so both routers route on history length alone.
* `inarvl_adapted.py:69-72` -> `(blur, exposure, artifact, detail) = (0.0, 0.0, 0.0, 1.0)`:
  "pristine image, maximum detail", constant.

Documented? `coordinator.py:655-657` states the placeholder. The other three writers do not, and
`live/adapter.py:15` documents the OPPOSITE of the truth: *"what the APPLICATION has actually
received: a cloud answer when its request completed, the device's own score otherwise"*.
`cascade_adapted.py:131-135` is the one arm that instruments the value it thresholds
(`stats["stream_scores_seen"]`, citing CLAUDE.md check 3). **Positive control on the audit:**
`sim/run.py:237-240` feeds the REAL measured scores from `dev_wall` (`:160-173`, `:419`), so the
offline simulator does NOT have this defect, and no score-reading arm's sim cell is comparable with
its live2 cell.

**2. `NetworkState.connected` is hard-coded `True` and is read as a gate at about twenty sites.
Largest blast radius found.** Writes: `live2/cstate.py:595`, `live/adapter.py:224`. Reads, every one
a routing or admission gate: `uniscale_adapted.py:84`, `ekya_adapted.py:135`,
`inarvl_adapted.py:83`, `routellm_adapted.py:95`, `hybrid_llm_adapted.py:74`,
`thinking_qwenvl_adapted.py:90`, `querystream_adapted.py:110`, `perllm_adapted.py:82`,
`videostorm_adapted.py:109`, `ecollm_adapted.py:125`, `cascade_adapted.py:136`,
`cascade_routing_adapted.py:125`, `r3streaming_adapted.py:107`, `constructed.py:59, 111, 142, 221,
341, 454, 560, 567`, `live2/arms_policy.py:633, 634, 817`, `live2/arms_published.py:156`.
**Composite finding:** `arms_policy.py:634-635` `if not s.network.connected: self.co.on_outage(...)`
is the ONLY production caller of `policy/coordinator.py:791 on_outage` in the tree, and it sits
behind this dead gate. So `Link.p_reachable_within_hs` (`policy/state.py:26`, default `1.0`) is
`1.0` everywhere, and the spec 7.5 reachability discount read at `policy/rollout.py:690`, `:756` and
`policy/closed_form.py:202` is a dead constant in every harness. `on_reconnect`
(`policy/coordinator.py:802`) has no production caller at all. Documented at
`fleet/links.py:9-11` as a design choice ("fixed, no variability, no outages"); NOT documented at
any of the twenty read sites, and `live/adapter.py:13-24`'s "WHAT IS LIVE" table omits
`streams[].network` entirely.

**3. `baselines/ekya_adapted.py:89` `return s + 0.0 * self._recall_gain(obs, bg)`.** A literal
`0.0` coefficient zeroes the term the comment two lines above says is added: *"Ekya's objective is
total accuracy across jobs; **ours adds** the background pool's served-recall count ... (adaptation
A4)"*. `_recall_gain` (`:62-72`) is fully implemented and called on every `score()`. Consequence:
`score()` becomes monotone non-decreasing in stream share, so in the thief loop (`:94-130`) any step
into `bg` is always reverted and any step out is always kept, and Ekya's characteristic joint
partition is one-directional. The clearest doc-versus-code contradiction in the tree.

**4. `live2/hybrid/value_reader.py:115`** returns `send=False` for every input, which also defeats
the Step-4 control this module declares for itself.

**5. `live2/cstate.py:260 CoordState.metrics`**: declared `field(default_factory=dict)`, written at
exactly one guarded site, read twice on the decision path.
**6. `live/adapter.py:233` with `:140-144`**: the same metric, with `except Exception: return {}`
substituting "KV cache empty" on any fetch failure.

**7. `baselines/simplestream_adapted.py:47 self.window_steps` is WRITE-ONLY**, and the arm's live2
registration cites that very parameter as the reason it ports. Same shape as `desired_tier`.

**8. `baselines/attentionstore_adapted.py:46, :48** `Session(sid, 0, HBM, last_access_s=0.0)`: a
literal `0` token count and a literal `0.0` access time feeding the two mechanisms the arm exists
for.

**9. `baselines/pensieve_adapted.py:47 tokens.setdefault(sid, 11000)`**: a magic 11,000-token
stand-in for a missing measured history size, on a charged path, four instances.

**10. `live2/arms_policy.py:792`** `d.demand = Demand().prior_from_profiles(self.pf)`: every
device's recall-demand rate is one frozen DEV prior, and the EWMA that would update it has no
caller.

**11. `live2/v5/cf_objective.py:280 DeficitCounters.weight()` returns exactly 1.0 for every device
in every arm but one.** This is D200 (1), found independently here.

**12. `policy/state.py:153 z_of()` -> `self.z.get(task, 0.0)`; `Device.z` (`:145`) is never written
on any production path.**
**13. `policy/state.py:41 HistoryBelief.staleness_s = 0.0`**, read on the decision path, written
nowhere by default.
**14. `live2/arms.py:82 self._caps` is WRITE-ONLY** (one code occurrence in the tree).
**15. `baselines/smoke/replay.py:102 device_answer_confidence=None`**: the smoke harness hard-codes
it and ignores `reads_device_answer`. The 2026-11-20 ruling that fixed this was applied to live2
only (`cstate.py:516 _device_confidence`); the smoke harness still has the old defect.
**16. `baselines/thinking_qwenvl_adapted.py:73`**: `rho` is a constant in all three harnesses, by
two independent routes.
**17. `baselines/inarvl_adapted.py:78-80, 94, 97`**: of the ten `fuse` inputs, seven are literal
constants typed into the source. All six text signals are hard zeros on the episodic path (`:78-80`)
and all four image signals are hard-coded on the recall path (`:97`); `energy_j=0.0` for every
candidate (`:61`), so the energy axis the paper routes on is inert (card A5 flags the last one).
Only `readiness_tokens` and `slack` vary.
**18. `baselines/constructed.py:96-103`**: B4's "query-type routing" takes the same branch on every
query in every harness, because `"D2" in have` is always true, so the DEVICE and single-shot
branches at `:101-108` are unreachable. The category never helps either: `LONG`/`SHORT` (`:84-85`)
do not contain any real trace category. Partly documented at `cstate.py:419-427`.

### Tier 2: real, outside the live2 decision path

**19. `e36e_fleet.py:853`**: the CLAUDE.md Step-4 negative control is defined and never called, and
it gates an 8,064-condition sweep at `:909-913`. `:862-870` prints `"Negative control PASS"` with no
computation. The code documents its own evasion at `:856-861`.
**20. `e36b_fleet.py:180-188`, `e36c_fleet.py:164-167`**: `refresh_ms()` returns 0.0 for every
reachable argument pair. CLAUDE.md's own cited precedent, confirmed in code.
**21. `policy/coordinator.py:704 competing_s=0.0`**: a hard zero the D122 v1.1 F3 fix missed, which
makes PRIORITY unreachable on the restore path even with `realistic_competing` on. Its own guard
test (`policy/tests/test_v11_fixes.py:338-355`) scans only three functions and not this one.
**22. `live2/touch_policy.py:108 TOUCH_PRICE_MODE = "reload-proxy"` is never assigned**, so
`touch_price_gpu_s_d162` (`:111`) is unreachable and the touch charge stays the whole-prefix price
that the module's own measurement (`:77-106`) calls 3.6x to 9.8x too high.
**23. `live2/arms_policy.py:790`**: an 8x unit error. `cstate.py:595` builds
`uplink_bps=d.uplink_mbps * 1e6 / 8.0`, already BYTES per second, and `:790` divides by 8 again
(212,500 B/s instead of 1,700,000 B/s), so every upload time the planner predicts is 8x too long.
`:639` additionally hard-codes the link constants for any device first seen on a recall query.
**24. `sim/run.py:253-255 latency_estimate_s`** is two constants, one a literal `0.0` that
`clockwork_adapted.py:58` reads as its queue estimate.
**25. `sim/run.py:250`**: recall work in flight is counted as `episodic` while `recall` carries a
literal 0.
**26. `live2/engine_actions.py:399-401 EXTERNAL_HIT_KEYS`** are CONSTRUCTED key names, so the
`host` belief is unreachable and the RELOAD lever has no trigger state. Documented at `:396-398`.
**27. `live2/coordinator.py:1653-1654`**: the dry service time is one constant for every episodic
request (literal `frame_count=1`, `load_pct=25`, so the arm's own frame count is ignored) and a
literal `"COLD"` for every recall request, so the warm-versus-cold distinction is absent from every
dry cell's timing. That constant becomes `lat["episodic"]`, which `cstate.py:19` advertises as "an
EWMA of MEASURED TTFTs".
**28. `baselines/profiles.py:94 C.__dict__.get("_CAD", (0.25, 0.5, 1.0))`**: `_CAD` is defined
nowhere, so the default is the only value ever used. Harmless today only because it happens to
equal `interface.CADENCES_S`.

---

## 3. What is NOT in this commit

The plumbing (item b), the decision-log diff (item c) and the rerun list (item e) follow as
separate commits. One result from the diff work belongs here because it changes how item (c) must
be run: **the committed `baseline_prescreen.json` cannot serve as the before side of this change.**
Its `_provenance.git_commit` is `62edb7fd82a5678c41d3a2296d2cb10c9e3539e0` (2026-11-20), and 875
commits separate that from the sha this work is built on, 59 of them touching
`coordinator.py`, `cstate.py`, `arms.py`, `arms_published.py` or `baselines/`. Both sides of the
diff must be run at ONE sha from two trees that differ only in this patch.

## 4. Open rulings this analysis raises

1. **D201 names two arms. Seven read the values.** `constructed.py` (B4) is one of them and is ours,
   not a published baseline. Whether the other five arms' committed cells are also superseded, and
   whether B4's are, is a user decision, not mine.
2. **Both cards specify a WITHIN-CLIP trajectory**; the harness window does not respect clip or
   episode boundaries. Measured on a 4-device 300 s dry cell with the device channel live: of 5,499
   calls carrying an episode key, **5,289 (96.2 per cent) spanned more than one EP-G episode**. So
   whether the two arms' feature window should be sliced to the current episode is a live question
   with a number behind it, and it changes both arms' decisions. Not decided here.
3. **A synthetic trace holds no committed device score**, so once scores are real, no arm whose
   published method reads one can be run on a synthetic cell. `tests/test_live2_coord.py`'s
   all-arm legality and fairness tests run every registered arm on exactly such a trace.
