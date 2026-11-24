# StudyPLACEHOLDER-FIX: D209 (2) hits 26, 22 and 6, fixed and proved

**Session A on flash, D209 (2), plus D211 step 1. Three files changed, all three owned by this
session: `live2/touch_policy.py` (hit 22), `live2/engine_actions.py` (hit 26), `live/adapter.py`
(hit 6). No other file was edited. Every proof runs on `git archive` checkouts of ONE literal
origin sha, never in the working tree, whose local HEAD `17bdf159` is not an ancestor of
origin/main and whose `live2/hybrid/` does not exist on disk.**

**Exactly what differs between the two trees, printed rather than asserted** (`diff -rq`, pycache
excluded): the three files above, plus ONE extra file present only in `after`,
`live2/d209_hit22_negctl.py`, which is the hit-22 negative-control runner. No module imports it and
it is invoked only by name, so it cannot reach a cell's decision path; it is named here because
"three files differ" would have been the wrong register for a four-entry diff.

Data: `results/orchestration/live2/placeholder_fixes/d209_placeholder_fix_proofs.json`.
Scripts: `experiments/orchestration/live2/d209_{digest_driver,unit_proofs,hit22_prices,step2b_rowdiff,negctl,assemble}.py`.
Triage this answers: `reports/study_placeholder_triage.md` (`2348b7c8`).
Probe this reads: `results/orchestration/live2/frozen_test/engine_probe_hit26/` (`8be7118`).
D211 pre-registration, frozen: `results/orchestration/live2/placeholder_fixes/d211_host_attribution_prereg.json`.

## Register conventions

Every claim is marked **OBSERVED** (measured in this run, or read in the code at the pinned sha) or
**CONSTRUCTED** (a counterfactual computed on observed inputs, or reasoned from the code). The
distinction carries the weight twice: hit 22's price comparison is a CONSTRUCTED counterfactual on
OBSERVED inputs, and hit 26's host-residency answer is OBSERVED in aggregate and unavailable per
request.

## The four headlines, before the detail

1. **ALL THREE FIXES ARE IN, AND NONE OF THEM MOVES A DRY DECISION. The reasons differ and the
   reasons are the result**, not a null: two of the three were established as inexpressible on a dry
   cell in Step 0 BEFORE the sweep, and the third is a gate that now reads the right number on a
   cell where no gate binds (0 of 2,267 touches refused at either price).
2. **AND THE LARGEST FINDING IS INCIDENTAL TO ALL THREE: a COMMENT-ONLY edit moves the rung-2 arm's
   dry decision log by 85 committed-key decisions and 11 rows.** Six runs of the same arm settle it:
   with the documented `id(obs)` cache key live, the tree's bytes decide the log; with it fixed,
   every tree reproduces the committed bar. **A rung-2 dry digest is not a property of the code
   until that fix is on**, so it cannot serve as a byte-identity bar or a Step 2b baseline for the
   final ladder.
3. **HIT 26 IS A PRE-REGISTERED ESCALATION AND THE ANSWER IS STRUCTURAL.** Host residency IS real on
   the live engine, 26 percent of its prompt tokens, but no per-request field distinguishes a host
   hit from a GPU hit, so a correct per-request host belief is NOT ACHIEVABLE on vLLM 0.31.0+cu129.
   No key was invented. The RELOAD lever is **UNEXERCISED for a structural reason, not a coding
   one**.
4. **HIT 6 IS WORSE THAN THE TRIAGE SAID AND MY FIX REACHES LESS OF IT THAN THE BRIEF ASSUMED.** The
   0.0 is permanent by a THIRD route that neither the triage nor the verified read census names:
   **the backend every reported live2 cell uses, `AsyncLive2Backend`, scrapes no /metrics at all.**
   Correcting the key name alone would have left the gate at 0.0 for ever and looked like a pass.
   The fix is correct and complete for the v1 `live/` harness and reaches ZERO live2 cells.
   **ESCALATED, with the exact change specified.**

## Mechanism verification (CLAUDE.md), recorded before the sweep

**Step 0, what would make this run uninterpretable, asked before it started.** Four things, and
two of them came back "wait" or "wrong", which is why the minute was worth spending.
(a) *Is the comparator about to change?* YES: origin/main moved from `1b99b6af` to `a976d5a4` to
`a02c0bc1` while this session worked, so both sides were pinned to ONE literal sha and the code
diff between that sha and the later one was checked to be empty for every module on the dry
decision path (only `canon.py`, `episodic_lib.py`, `d176_robot_headline.py` and three proof shell
scripts moved).
(b) *Is the tree I am building from the code I think it is?* NO: the working tree's HEAD
`17bdf159` is not an ancestor of origin/main, `live2/hybrid/` is absent from it, and neither
`engine_actions.py` nor `touch_policy.py` exists on disk there. Every tree used here is a
`git archive` of the pinned sha.
(c) *Does the mechanism have a reachable path at this size and in this regime?* For hit 22 YES,
for hits 26 and 6 NO on a dry cell, and that was established BEFORE the sweep rather than
discovered in a null: `external_cached_tokens_of` returns None on both sides for every possible
usage block, and `adapter` is **not even imported** on the dry path (measured: after importing
`test_hybrid` and registering all v6 modules, `"adapter" in sys.modules` is False).
(d) *Is a digest comparable across the two sides?* Only within one recipe, so the committed recipe
`cf_pd_one_cell.py --cutoff-off` with the posted knobs is used unchanged on both sides, and its
own positive control (`covex-v6-base` must read `af8befb9420ad86a` / 12,085) is checked first.

**Step 1, the causal chain, per hit.**

*Hit 22.* If a touch's budget gate is priced by a quantity that scales with the prefix
(`costs.recall_gpu_s(prefix, tier)`, StudyRH5 Part A isolated reload TTFT) while the work a warm
touch actually does is a handful of uncached tokens (D174 (1), spec section 6, D160 pricing by
predicted cache state), then the gate refuses touches whose true charge the budget can afford;
refused touches leave warm histories un-refreshed, so vLLM's LRU evicts them, so later recalls pay
a cold rebuild instead of a warm hit. Correcting the gate's price to the ruled charge therefore
changes which touches are issued, which changes the decision log. Every link is in D174 (1),
D160 and spec v6 section 6.

*Hit 26.* If the engine exposes a per-request field distinguishing a host hit from a GPU hit
(D150's belief corrector, spec v5 lever 5), then a zero-GPU-reuse request over a built prefix can
be classified HOST rather than COLD, which puts the session at HOST-WARM, which is the only state
at which the RELOAD lever is offered. The chain is sound; the first link is the one the probe
tests, and it fails.

*Hit 6.* If the admission gate's KV-pressure input is the engine's observed KV usage, then a
failed or mis-keyed read must not be substituted by the most permissive value in the range,
because an arm would then admit work the engine has no room for. The read sites are
`arms_v6cf.py:306` (rung 4, no fallback term), `preble_adapted.py:57` and `constructed.py:416`
(partially masked by their own `max(...)` against a queue-derived term) and
`uniscale_adapted.py:63` (a raw feature in a linear model, hence a dead feature at 0.0).

**AND THREE OF THOSE FOUR ARE NOT REPORTED ARMS, which a ruling of 2026-11-23 settled while this
work was in flight: the committed `BASELINE_MATRIX` governs the paper's baseline set, and `preble`,
`b9` and `uniscale` are not in it.** So among reported arms hit 6 reaches **ONLY RUNG 4**: rungs 2
and 3 have zero occurrences of `gpu_kv_fraction` (`arms_v6state.py`, `arms_v6fair.py`,
`arms_v6rr.py`, `release_recheck.py`, `arms_v6c5.py`), and base and rules read only
`latency_estimate_s`, `queued_by_class` and `running_by_class`. The three non-matrix arms are kept
in the tables below, labelled NOT A REPORTED ARM, rather than dropped: **the defect in them is real
whether or not the arm is printed**, and their cells are superseded and unreported rather than
clean. `engine_actions.py:288` (`hold_back`) is deliberately NOT counted as a read at all: it has
**no callers** (escalation E4).

**Step 2, each link instantiated.** `engine_actions.py:288` (`hold_back`) is deliberately NOT
counted as a read: it has **no callers** in the tree, its own definition at `:276` and a docstring
mention at `:21` being its only two occurrences. That is a separate ABSENT-MECHANISM finding and
is reported, not fixed, below.

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence |
|---|---|---|---|---|
| touch gate price (hit 22) | `touch_policy.price_for_touch` -> `should_touch`'s `budget_ok(price)` | before 0.2431 to 0.6714 GPU-s, rising with prefix; after 0.00273647 GPU-s, constant | YES, and the SHAPE changes: independent of prefix after | unit proof ladder at 7k/11k/17k/21k tokens, both trees |
| touch budget charge (hit 22, for contrast) | `coordinator.py:1175` `d162_price.price_gpu_s(15, ..., "uncached-only")` | 0.00273647 GPU-s, UNCHANGED by this work | n/a, it was already correct | `d162_price.py:149-164`; drift check against the committed gate PASSES on both sides |
| per-request host signal (hit 26) | `engine_actions.external_cached_tokens_of(usage)` | **None on every possible input, both trees** | NO, and that is the finding | probe README; `UsageInfo` / `PromptTokenUsageInfo` at `protocol.py:121-140` |
| aggregate host residency (hit 26) | `vllm:prompt_tokens_by_source_total{source="external_kv_transfer"}` | 4,943,072 of 18,707,015 prompt tokens, 26.4 percent | n/a, single capture | `metrics_scrape_h100.txt` |
| KV-pressure input (hit 6) | `HttpBackend._fetch_metrics` -> `cloud.gpu_kv_fraction` | before 0.0 on 4 of 5 probe states; after 0.7215 / 0.4242 / 0.4242 last-good / 1.0 / 1.0 | YES | five-state unit proof, both trees |
| KV-pressure input INSIDE live2 (hit 6) | `coordinator.py:489` `st.metrics = be.metrics()` with `be` = `AsyncLive2Backend` | **no `vllm:` key at any time: ABSENT** | n/a | `AsyncLive2Backend` is not an `HttpBackend` subclass, contains no `/metrics`, and its `metrics()` returns build and wire statistics |

**Step 2b, the switch reaching a decision: run per hit, on a dry s4 cell, before any scoring.**
See the tables below. Hit 22 moves decisions; hits 26 and 6 move none, and that is reported as an
**ABSENT LINK in Step 2b's own sense, never as a negative**: for hit 26 because the quantity's
value is identical on both sides by measurement, and for hit 6 because the module is not loaded on
the dry path at all.

**Step 3, one traced unit per hit.** Below, in each hit's section.

**Step 4, the negative control, per hit.** The `before` tree IS the negative control, and it is a
measured one rather than a monkey-patch: it is the same code with the fix absent, run through the
same recipe on the same cell. For hit 6 the control is also run inside the unit proof, which
records what the old `{}` return hands a reader at each of the five states (0.0 every time).

**Step 5, the alternative explanation.** For hit 22 the headline ("decisions move") could be
produced by (a) the corrected gate admitting touches the old price refused [the claimed
mechanism], or (b) any change at all to a module imported on the decision path, through import
order or a changed constant. What distinguishes them: the per-hit attribution run, in which the
tree carrying ONLY hits 26 and 6 is byte-identical to `before` on the same arms, so a mere edit to
an imported module does not move a digest; and the touch counters, which show the refusal count
falling and the issue count rising in the direction the mechanism predicts rather than an arbitrary
reshuffle.

## Results consistency check

**1. Cross-check against committed measurements.** The `before` side is the audit: it must
reproduce the committed bars of the same recipe, which are listed in `research/EXPERIMENTS.md`
under StudyFROZEN-test.

| quantity | this run (before side) | prior committed | source of prior | ratio | agree? |
|---|---|---|---|---|---|
| `covex-v6-base` digest / rows | `af8befb9420ad86a` / 12,085 | `af8befb9420ad86a` / 12,085 | EXPERIMENTS.md StudyFROZEN-test; c5attr_digest_proofs.json P1 | 1.000 | AGREE |
| `covex-v6-state-uo` digest / rows | `639cd15ed38c9da0` / 14,207 | `9a4be873eb3c5fba` / 14,218 | c5attr_digest_proofs.json P1 | 0.9992 | **DISAGREE** |
| `covex-v6-state-uo-c5attr` digest / rows | `639cd15ed38c9da0` / 14,207 | `9a4be873eb3c5fba` / 14,218 | EXPERIMENTS.md StudyFROZEN-test (ALONE; 639cd15ed38c9da0 / 14,207 under concurrency, d190_rung4_r3_proofs.py:192-197) | 0.9992 | **DISAGREE** |
| `covex-v6-fair-c5attr` digest / rows | `12e4f73ce0ebd865` / 13,812 | `12e4f73ce0ebd865` / 13,812 | EXPERIMENTS.md StudyFROZEN-test; D208 (1) rung-3 bar | 1.000 | AGREE |
| `covex-v6-cf-c5attr` digest / rows | `f5b627392839527c` / 14,470 | `f5b627392839527c` / 14,470 | EXPERIMENTS.md StudyFROZEN-test, the post-D206 rung-4 bar | 1.000 | AGREE |
| `v5-rules-2` digest / rows | `18067c4c66bb44b8` / 11,955 | `18067c4c66bb44b8` / 11,955 | c5attr_digest_proofs.json P1 | 1.000 | AGREE |
| `b7-edf-feasibility` digest / rows | `b9aadd1c3a2b26d5` / 12,265 | `b9aadd1c3a2b26d5` / 12,265 | c5attr_digest_proofs.json P1 | 1.000 | AGREE |
**Reading of the two DISAGREE rows, and it is the whole of the load finding in one place.** The only
two arms that fail to reproduce their committed bar on the `before` side are the two rung-2-family
arms, and their committed bar is explicitly the value measured ALONE
(`d190_rung4_r3_proofs.py:192-197`), while `639cd15ed38c9da0` / 14,207 is explicitly the value that
proof measured under concurrency. So the control's disagreement is a KNOWN, COMMITTED property of
that arm and not a discrepancy to choose between: with `--diag-epoch-cache-key` both trees
reproduce the committed `9a4be873eb3c5fba` / 14,218 exactly. Five of the seven comparators AGREE at
ratio 1.000, including the post-D206 rung-4 bar, which is the positive control that says the check
itself is sound.

**2. Physical plausibility.** The only rates here are prices, not measurements. The ruled touch
charge implies 1 / 0.0001824312597782467 = 5,482 tok/s, which agrees with the committed 5,600
tok/s cold-prefill rate to 2 percent (`d162_price.py:122-125`); the reload proxy it replaces
implies 7,000 tokens of prefill work for a request the engine measured at 3 uncached tokens, a
rate claim 2,333x off its own measurement. The conservative unknown KV fraction is 1.0, a
dimensionless fraction at the end of its range, so no rate claim attaches to it.

**3. Distribution sanity.** The touch price is reported with its full spread, and the shape change
is the point: **before, the price is a distribution that tracks prefix length; after, it is a
constant** by construction. A constant is normally the alarm; here it is the specification, and the
quantity that must still carry a distribution is the PREFIX LENGTH, which is reported beside it to
show the inputs did vary. The committed module's own quoted overcharge of "3.6x to 9.8x" is
against the INTERMEDIATE `d162-warm-hit` price (0.070534 GPU-s, which carries the intercept):
0.2431 / 0.070534 = 3.45 and 0.6714 / 0.070534 = 9.52. Against the price D174 (1) actually rules,
the overcharge is **88.8x at a 7k prefix rising to 245.4x at 21k**, because the intercept D174 (1)
excludes is 96 percent of the `d162-warm-hit` number. A reader who carries "3.6x to 9.8x" forward
will understate this fix by a factor of 25.8.

**4. Definition audit.** `touch`: one request re-presenting the built prefix with
`max_tokens = 1`, carrying no new frames; `TOUCH_UNCACHED_TOKENS = 15` is the MAX uncached tokens
measured over 1,246 touches on the covex-v6-state s4 cell (p50 was 3), used rather than the median
so the price stays an upper bound. `uncached-only` charge: `PER_UNCACHED_S * u`, no intercept, no
queue term, D174 (1). `gpu_kv_fraction`: the engine's KV-cache utilisation fraction in [0, 1];
vLLM renamed the gauge from `gpu_cache_usage_perc` to `kv_cache_usage_perc` between the build the
code was written against and 0.31.0, and both spellings now resolve to the same field. A dry cell
has no engine and therefore no KV telemetry, which is a THIRD definition of the same field name
and is exactly why the never-0.0 policy was NOT pushed into `cstate.py` (see the escalation).
Recipe and digest: the committed `cf_pd_one_cell.py --cutoff-off` recipe, unchanged.

**5. Claim linkage.** Hit 22 bears on FORMULATION.md's refresh/maintenance cost being
representation- and state-dependent and on spec v6 section 6: a gate that prices a warm touch as a
cold reload cannot express the maintenance cost the formulation posits, so the fix SUPPORTS the
ability to test that claim and is not itself evidence for it. Hit 26 bears on the state layer
(D26, D44, D150): it WEAKENS the testability of the HOST-WARM/RELOAD limb on this engine, and the
right reading is Rule 2 **unexercised**, structurally. Hit 6 bears on bounded GPU capacity as an
input (D29, D56): on the v1 path it restores the input; on the live2 path it reports that the input
was never connected.

**6. Proxy validity.** Two proxies are declared. (i) The paired price column for a touch the run
did not take is a CONSTRUCTED counterfactual on OBSERVED inputs: the same prefix, the same belief,
the same budget, at the same instant, asked a second question. It is valid for "would this touch
have been refused at the other price" and NOT valid as a count of touches the corrected arm
issues, which is why the arm's own counters are reported beside it. (ii) The host-residency share
is a single /metrics capture during one `covex-v6-base` s4 `_kv0.25` cell, cumulative since server
start; it is valid for "host hits are frequent, not negligible" and invalid for any per-cell or
per-arm rate.

**7. Validate the control, not only the result.** The control here is the `before` tree, and it is
audited against committed values before the comparison is read (check 1 above). The positive
control is the committed-digest match on arms that must NOT move.

## Byte identity, the gate

**Scope, which narrowed while this ran.** A ruling of 2026-11-23 fixed the paper's baseline set to
the committed `BASELINE_MATRIX` ACTIVE arms plus `kvflow-prefetch`, `cascade-routing` and
`device-only`, with `r3-streaming` out. `preble`, `b9` and `uniscale` are NOT in that set; they were
already running when the ruling arrived and their pairs are kept below LABELLED NOT A REPORTED ARM
rather than deleted, because the hit-6 defect in them is real whether or not the arm is printed and
the user ruled that such defects stay on record with their cells superseded and unreported.

**Two arms errored on their FIRST pair, identically on both sides, and on a data file rather than on
code**: `simplestream` and `confidence-cascade` both wanted
`results/dashcam/study_d3_nexar/d3_requests_h100nvl.jsonl.gz`, which my size-capped checkout had not
materialised. That is a gap in my tree, not a result: an identical `FileNotFoundError` on both sides
is not a digest. The file was supplied from the pinned sha and both arms were rerun; their reruns are
in their own tables so the reader can see which number came from which pass.

**Host load, with magnitudes, as asked.** These cells ran 10 at a time on flash at `/proc/loadavg`
1-minute values between 10.65 and 25.46. That is above the 9.00 the committed record documents, and
it matters for exactly one arm family: see the OPERATIONAL FINDING. The positive control is that
`covex-v6-base`, `covex-v6-rules`, `v5-rules-2`, `b7-edf-feasibility` and `covex-v6-cf-c5attr` all
reproduce their committed bars EXACTLY at that load, which is what says the load did not perturb
them.

**All three fixes: `before` against `after`, 46 dry s4 cells, one cell per process, committed recipe**

| arm | role | before | rows | after | rows | identical? |
|---|---|---|---|---|---|---|
| `covex-v6-base` | rung 0 (base) | `af8befb9420ad86a` | 12,085 | `af8befb9420ad86a` | 12,085 | **YES** |
| `covex-v6-rules` | rung 1 (rules) | `18067c4c66bb44b8` | 11,955 | `18067c4c66bb44b8` | 11,955 | **YES** |
| `covex-v6-state-uo` | rung 2 family | `639cd15ed38c9da0` | 14,207 | `9a4be873eb3c5fba` | 14,218 | **NO** |
| `covex-v6-state-uo-c5attr` | RUNG 2 | `639cd15ed38c9da0` | 14,207 | `9a4be873eb3c5fba` | 14,218 | **NO** |
| `covex-v6-fair-c5attr` | RUNG 3 | `12e4f73ce0ebd865` | 13,812 | `12e4f73ce0ebd865` | 13,812 | **YES** |
| `covex-v6-fair-c5attr-rr` | reported baseline | `3dd6d89c65050ab4` | 13,841 | `3dd6d89c65050ab4` | 13,841 | **YES** |
| `covex-v6-cf-c5attr` | rung 4 family, reads `gpu_kv_fraction` | `f5b627392839527c` | 14,470 | `f5b627392839527c` | 14,470 | **YES** |
| `covex-v6-cf-pd-c5attr` | RUNG 4, reads `gpu_kv_fraction` | `9a4be873eb3c5fba` | 14,218 | `9a4be873eb3c5fba` | 14,218 | **YES** |
| `v5-rules-2` | reported baseline | `18067c4c66bb44b8` | 11,955 | `18067c4c66bb44b8` | 11,955 | **YES** |
| `hybrid-F-lhreq-noc3` | reported baseline | `af8befb9420ad86a` | 12,085 | `af8befb9420ad86a` | 12,085 | **YES** |
| `b7-edf-feasibility` | BASELINE_MATRIX active | `b9aadd1c3a2b26d5` | 12,265 | `b9aadd1c3a2b26d5` | 12,265 | **YES** |
| `always-cloud-fcfs` | BASELINE_MATRIX active | `c7f86bb7755828de` | 12,253 | `c7f86bb7755828de` | 12,253 | **YES** |
| `edf` | BASELINE_MATRIX active | `9db366ac8f684d45` | 16,327 | `9db366ac8f684d45` | 16,327 | **YES** |
| `llf` | BASELINE_MATRIX active | `961be8fe4942d86b` | 14,075 | `961be8fe4942d86b` | 14,075 | **YES** |
| `mooncake` | BASELINE_MATRIX active | `7544b3aa16433c70` | 12,742 | `7544b3aa16433c70` | 12,742 | **YES** |
| `attentionstore-prefetch` | BASELINE_MATRIX active | `b563cf7612fd1e02` | 46,931 | `b563cf7612fd1e02` | 46,931 | **YES** |
| `querystream-proactive` | BASELINE_MATRIX active | `a0b9e14e513c621c` | 12,646 | `a0b9e14e513c621c` | 12,646 | **YES** |
| `warm-all-lru` | BASELINE_MATRIX active | `751381e72502fffe` | 17,205 | `751381e72502fffe` | 17,205 | **YES** |
| `eco-llm` | BASELINE_MATRIX active | `f32fa95c6953c64e` | 12,253 | `f32fa95c6953c64e` | 12,253 | **YES** |
| `preble` | **NOT a reported arm** (not in BASELINE_MATRIX; run before the ruling, kept as a noted gap), reads `gpu_kv_fraction` | `538f987a2006e5c2` | 12,742 | `538f987a2006e5c2` | 12,742 | **YES** |
| `b9` | **NOT a reported arm** (not in BASELINE_MATRIX; run before the ruling, kept as a noted gap), reads `gpu_kv_fraction` | `41176be5db7b16f3` | 12,712 | `41176be5db7b16f3` | 12,712 | **YES** |
| `uniscale` | **NOT a reported arm** (not in BASELINE_MATRIX; run before the ruling, kept as a noted gap), reads `gpu_kv_fraction` | `565efa5a5bded966` | 5,963 | `565efa5a5bded966` | 5,963 | **YES** |

Arms whose digest MOVED: `covex-v6-state-uo`, `covex-v6-state-uo-c5attr`

Distinct before-side digests over 24 arms: 19, so the digest discriminates arms and an identity is not a degenerate hash.

Cells that did not produce a digest (reported, not dropped):
- `simplestream`: before "FileNotFoundError: [Errno 2] No such file or directory: '/tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/befo", after "FileNotFoundError: [Errno 2] No such file or directory: '/tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/afte"
- `confidence-cascade`: before "FileNotFoundError: [Errno 2] No such file or directory: '/tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/befo", after "FileNotFoundError: [Errno 2] No such file or directory: '/tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/afte"

**`streamscout` and `cascade-routing`, rerun after their missing committed inputs were supplied**

| arm | role | before | rows | after | rows | identical? |
|---|---|---|---|---|---|---|
| `streamscout` | BASELINE_MATRIX active | `30b2806a117c9c57` | 12,249 | `30b2806a117c9c57` | 12,249 | **YES** |
| `cascade-routing` | BASELINE_MATRIX active | `2a8ea8279c7e2c69` | 12,249 | `2a8ea8279c7e2c69` | 12,249 | **YES** |

Arms whose digest MOVED: none

Distinct before-side digests over 2 arms: 2, so the digest discriminates arms and an identity is not a degenerate hash.

**`confidence-cascade`, rerun after its missing committed input was supplied (its first pair errored IDENTICALLY on both sides)**

| arm | role | before | rows | after | rows | identical? |
|---|---|---|---|---|---|---|
| `confidence-cascade` | BASELINE_MATRIX active | `775125d173c5e00d` | 3,104 | `775125d173c5e00d` | 3,104 | **YES** |

Arms whose digest MOVED: none

Distinct before-side digests over 1 arms: 1, so the digest discriminates arms and an identity is not a degenerate hash.

**`simplestream`, rerun after its missing committed input was supplied (its first pair errored IDENTICALLY on both sides, on a data file absent from the checkout, not on the code)**

| arm | role | before | rows | after | rows | identical? |
|---|---|---|---|---|---|---|
| `simplestream` | BASELINE_MATRIX active | `870a3c3586d1b537` | 12,253 | `870a3c3586d1b537` | 12,253 | **YES** |

Arms whose digest MOVED: none

Distinct before-side digests over 1 arms: 1, so the digest discriminates arms and an identity is not a degenerate hash.

**The five BASELINE_MATRIX arms added after the set was fixed: `before` against `after`**

| arm | role | before | rows | after | rows | identical? |
|---|---|---|---|---|---|---|
| `lmcache` | BASELINE_MATRIX active | `2b789696e98821c4` | 37,080 | `2b789696e98821c4` | 37,080 | **YES** |
| `kvflow-prefetch` | BASELINE_MATRIX active | `0e3ba03d2e7ff3b3` | 32,316 | `0e3ba03d2e7ff3b3` | 32,316 | **YES** |
| `device-only` | BASELINE_MATRIX active | `e1d2340a47d303c5` | 489 | `e1d2340a47d303c5` | 489 | **YES** |

Arms whose digest MOVED: none

Distinct before-side digests over 5 arms: 3, so the digest discriminates arms and an identity is not a degenerate hash.

Cells that did not produce a digest (reported, not dropped):
- `streamscout`: before "FileNotFoundError: [Errno 2] No such file or directory: '/tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/befo", after "FileNotFoundError: [Errno 2] No such file or directory: '/tmp/claude-1001/-home-pragya-Desktop-FM-switching/8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/afte"
- `cascade-routing`: before "RuntimeError: device_confidence's committed table is EMPTY; an arm declaring reads_device_answer would be charged the device-answer wait and handed None for eve", after "RuntimeError: device_confidence's committed table is EMPTY; an arm declaring reads_device_answer would be charged the device-answer wait and handed None for eve"

**ATTRIBUTION: `before` against `after_no22` (hits 26 and 6 ONLY, `touch_policy.py` byte-identical)**

| arm | role | before | rows | after | rows | identical? |
|---|---|---|---|---|---|---|
| `covex-v6-base` | rung 0 (base) | `af8befb9420ad86a` | 12,085 | `af8befb9420ad86a` | 12,085 | **YES** |
| `covex-v6-state-uo-c5attr` | RUNG 2 | `639cd15ed38c9da0` | 14,207 | `9a4be873eb3c5fba` | 14,218 | **NO** |
| `covex-v6-fair-c5attr` | RUNG 3 | `12e4f73ce0ebd865` | 13,812 | `12e4f73ce0ebd865` | 13,812 | **YES** |
| `covex-v6-cf-pd-c5attr` | RUNG 4, reads `gpu_kv_fraction` | `9a4be873eb3c5fba` | 14,218 | `9a4be873eb3c5fba` | 14,218 | **YES** |
| `preble` | **NOT a reported arm** (not in BASELINE_MATRIX; run before the ruling, kept as a noted gap), reads `gpu_kv_fraction` | `538f987a2006e5c2` | 12,742 | `538f987a2006e5c2` | 12,742 | **YES** |
| `b9` | **NOT a reported arm** (not in BASELINE_MATRIX; run before the ruling, kept as a noted gap), reads `gpu_kv_fraction` | `41176be5db7b16f3` | 12,712 | `41176be5db7b16f3` | 12,712 | **YES** |
| `uniscale` | **NOT a reported arm** (not in BASELINE_MATRIX; run before the ruling, kept as a noted gap), reads `gpu_kv_fraction` | `565efa5a5bded966` | 5,963 | `565efa5a5bded966` | 5,963 | **YES** |

Arms whose digest MOVED: `covex-v6-state-uo-c5attr`

Distinct before-side digests over 7 arms: 7, so the digest discriminates arms and an identity is not a degenerate hash.


### CONSOLIDATED GATE: one verdict per arm, across every pass

| arm | role | before | rows | after | rows | verdict |
|---|---|---|---|---|---|---|
| `always-cloud-fcfs` | BASELINE_MATRIX active | `c7f86bb7755828de` | 12,253 | `c7f86bb7755828de` | 12,253 | **IDENTICAL** |
| `attentionstore-prefetch` | BASELINE_MATRIX active | `b563cf7612fd1e02` | 46,931 | `b563cf7612fd1e02` | 46,931 | **IDENTICAL** |
| `b7-edf-feasibility` | BASELINE_MATRIX active | `b9aadd1c3a2b26d5` | 12,265 | `b9aadd1c3a2b26d5` | 12,265 | **IDENTICAL** |
| `b9` | **NOT a reported arm** | `41176be5db7b16f3` | 12,712 | `41176be5db7b16f3` | 12,712 | **IDENTICAL** |
| `cascade-routing` | BASELINE_MATRIX active | `2a8ea8279c7e2c69` | 12,249 | `2a8ea8279c7e2c69` | 12,249 | **IDENTICAL** |
| `confidence-cascade` | BASELINE_MATRIX active | `775125d173c5e00d` | 3,104 | `775125d173c5e00d` | 3,104 | **IDENTICAL** |
| `covex-v6-base` | rung 0 (base) | `af8befb9420ad86a` | 12,085 | `af8befb9420ad86a` | 12,085 | **IDENTICAL** |
| `covex-v6-cf-c5attr` | rung 4 family | `f5b627392839527c` | 14,470 | `f5b627392839527c` | 14,470 | **IDENTICAL** |
| `covex-v6-cf-pd-c5attr` | RUNG 4 | `9a4be873eb3c5fba` | 14,218 | `9a4be873eb3c5fba` | 14,218 | **IDENTICAL** |
| `covex-v6-fair-c5attr` | RUNG 3 | `12e4f73ce0ebd865` | 13,812 | `12e4f73ce0ebd865` | 13,812 | **IDENTICAL** |
| `covex-v6-fair-c5attr-rr` | reported baseline | `3dd6d89c65050ab4` | 13,841 | `3dd6d89c65050ab4` | 13,841 | **IDENTICAL** |
| `covex-v6-rules` | rung 1 (rules) | `18067c4c66bb44b8` | 11,955 | `18067c4c66bb44b8` | 11,955 | **IDENTICAL** |
| `covex-v6-state-uo` | rung 2 family | `639cd15ed38c9da0` | 14,207 | `9a4be873eb3c5fba` | 14,218 | **MOVED** |
| `covex-v6-state-uo-c5attr` | RUNG 2 | `639cd15ed38c9da0` | 14,207 | `9a4be873eb3c5fba` | 14,218 | **MOVED** |
| `device-only` | BASELINE_MATRIX active | `e1d2340a47d303c5` | 489 | `e1d2340a47d303c5` | 489 | **IDENTICAL** |
| `eco-llm` | BASELINE_MATRIX active | `f32fa95c6953c64e` | 12,253 | `f32fa95c6953c64e` | 12,253 | **IDENTICAL** |
| `edf` | BASELINE_MATRIX active | `9db366ac8f684d45` | 16,327 | `9db366ac8f684d45` | 16,327 | **IDENTICAL** |
| `hybrid-F-lhreq-noc3` | reported baseline | `af8befb9420ad86a` | 12,085 | `af8befb9420ad86a` | 12,085 | **IDENTICAL** |
| `kvflow-prefetch` | BASELINE_MATRIX active | `0e3ba03d2e7ff3b3` | 32,316 | `0e3ba03d2e7ff3b3` | 32,316 | **IDENTICAL** |
| `llf` | BASELINE_MATRIX active | `961be8fe4942d86b` | 14,075 | `961be8fe4942d86b` | 14,075 | **IDENTICAL** |
| `lmcache` | BASELINE_MATRIX active | `2b789696e98821c4` | 37,080 | `2b789696e98821c4` | 37,080 | **IDENTICAL** |
| `mooncake` | BASELINE_MATRIX active | `7544b3aa16433c70` | 12,742 | `7544b3aa16433c70` | 12,742 | **IDENTICAL** |
| `preble` | **NOT a reported arm** | `538f987a2006e5c2` | 12,742 | `538f987a2006e5c2` | 12,742 | **IDENTICAL** |
| `querystream-proactive` | BASELINE_MATRIX active | `a0b9e14e513c621c` | 12,646 | `a0b9e14e513c621c` | 12,646 | **IDENTICAL** |
| `simplestream` | BASELINE_MATRIX active | `870a3c3586d1b537` | 12,253 | `870a3c3586d1b537` | 12,253 | **IDENTICAL** |
| `streamscout` | BASELINE_MATRIX active | `30b2806a117c9c57` | 12,249 | `30b2806a117c9c57` | 12,249 | **IDENTICAL** |
| `uniscale` | **NOT a reported arm** | `565efa5a5bded966` | 5,963 | `565efa5a5bded966` | 5,963 | **IDENTICAL** |
| `v5-rules-2` | reported baseline | `18067c4c66bb44b8` | 11,955 | `18067c4c66bb44b8` | 11,955 | **IDENTICAL** |
| `warm-all-lru` | BASELINE_MATRIX active | `751381e72502fffe` | 17,205 | `751381e72502fffe` | 17,205 | **IDENTICAL** |

**Arms with a verdict: 29. MOVED: `covex-v6-state-uo`, `covex-v6-state-uo-c5attr`.**


## HIT 26, `live2/engine_actions.py:399-401`: the probe answers, and the answer is structural

**What the probe settled (OBSERVED, from `engine_probe_hit26/`, one read-only GET on the live H100,
vLLM 0.31.0+cu129, Qwen3-VL-32B, native CPU offload, during a `covex-v6-base` s4 `_kv0.25` cell).**

*(a) Is host residency OBSERVED at all?* **YES, and it is large: 26.4 percent of the engine's prompt
tokens.** `vllm:prompt_tokens_by_source_total{source="external_kv_transfer"}` = 4,943,072 against
`local_cache_hit` 10,094,768 and `local_compute` 3,669,175, total 18,707,015;
`vllm:external_prefix_cache_hits_total` 4,945,760 of 8,618,089 queries; 1,847 CPU-to-GPU loads
moving 1.2965e12 bytes; `vllm:kv_offload_cpu_cache_usage_perc` 0.0347. The committed
0-of-15,914 host-belief census was therefore NOT telling us the host tier is unused. It was
telling us the belief could not see it.

*(b) Is a correct PER-REQUEST host belief ACHIEVABLE on this engine?* **NO.** The per-request
schema is fixed by the installed source (`vllm/entrypoints/serve/engine/protocol.py:121-140`):
`UsageInfo` carries `prompt_tokens`, `total_tokens`, `completion_tokens`,
`prompt_tokens_details`, `completion_tokens_details`, and `PromptTokenUsageInfo` carries exactly
`cached_tokens`, `created_cache_tokens`, `multimodal_tokens`. A host hit and a GPU hit are both
folded into `cached_tokens` and cannot be separated from it; the counter side agrees exactly
(`vllm:prompt_tokens_cached_total` 15,037,840 = local_cache_hit + external_kv_transfer). None of
the five guessed `EXTERNAL_HIT_KEYS` exists.

**So the pre-registered escalation fires, and it is not the clean negative it was written as.** It
is not "no host key exists" (one does, in aggregate) and it is not "the key name was wrong" (there
is no per-request key to name). **No key was invented, and no counter-differencing was wired into a
decision path**: differencing `external_prefix_cache_hits_total` between requests is exact only
with a single request in flight, and `num_requests_running` was 3 at capture in a 16-device
three-type cell, so attributing a counter delta to one request would manufacture a signal the
engine does not emit.

**THE FINDING, in Rule 2's terms: the RELOAD lever is UNEXERCISED FOR A STRUCTURAL REASON.**
RELOAD is offered only at HOST-WARM; no per-request signal can place a session at HOST-WARM on
vLLM 0.31.0; therefore the lever is unreachable in principle on this engine, not unreachable
because of a coding defect. That is a statement about the engine's usage schema and it is not a
negative about the policy. It also means the belief's `cold` branch should be read as **"not in
GPU KV"**: an upper bound on reconstruction cost and a LOWER bound on residency.

**What changed in the file.** Register only, CONSTRUCTED to OBSERVED. The UNVERIFIED block is
replaced by the probe's findings with its source path; `EXTERNAL_HIT_KEYS` is labelled REFUTED
and `EXTERNAL_HIT_KEYS_REFUTED_BY_PROBE = True` is added; the observed per-request field list,
the aggregate host-residency key names (REPORTING ONLY, read by no decision) and
`PER_REQUEST_HOST_SIGNAL_AVAILABLE = False` are recorded; the `cold` branch's reason string and the
PROVISIONAL paragraph are corrected to say what is now measured.

**The tuple was NOT emptied, and that was a deliberate reversal.** Emptying it was written first
and then undone: `confirm_engine_actions_32b.py:1358` indexes `EA.EXTERNAL_HIT_KEYS[0]` to prove
the lookup surfaces an external key when one is present, and `:684` reports the probed list. That
file belongs to another session, and an empty tuple makes its self-test raise `IndexError`. Taking
the names out is a one-line follow-up for that file's owner and is not worth silently breaking
someone else's proof for.

**Trace, one representative belief update (both trees, identical):**

```
usage block (the real shape):
  prompt_tokens 10001, prompt_tokens_details {cached_tokens: 0, created_cache_tokens: 0,
                                              multimodal_tokens: 0}
external_cached_tokens_of(usage)      -> None        (BEFORE: None, AFTER: None)
session: built_tokens 5000, belief gpu=1.0
belief_update_from_cached_tokens(s, cached_tokens=0, prompt_tokens=10001, external=None)
  ct == 0, built 5000 > 0, offered 10001 >= built  -> the demotion guard does not fire
  external_tokens falsy                            -> branch "cold"
  before gpu -> after cold, changed True
and with a hypothetical per-request host signal, to show the host branch is live code whose only
missing part is its INPUT (this is a Step 2 read, not a decision any cell took):
  external_tokens=4096                              -> after "host"
```

*(c) HOW MANY COMMITTED RUNG-2-AND-ABOVE DECISIONS WOULD HAVE DIFFERED, measured on a dry cell,
not estimated:* **ZERO**, and for two independent reasons, both measured rather than argued. First,
`external_cached_tokens_of` returns `None` for every input on both sides, so the quantity the
corrector reads is identical. Second, on a dry cell the belief corrector cannot fire at all: there
is no engine, so `cached_tokens` is `None`, which the corrector treats as NO EVIDENCE by design.
Under Step 2b's own rule this is an **ABSENT LINK, not a negative**: hit 26 is a register
correction, and the thing worth reporting about it is the structural answer in (b), not a
decision count.

## HIT 22, `live2/touch_policy.py`: the mode flipped, and the defect was a gate priced unlike the charge

**The correction, and where.** `TOUCH_PRICE_MODE` was assigned `"reload-proxy"` with the comment
"DEFAULT, the committed behaviour; nothing changes" at `touch_policy.py:108`. It is now
**`TOUCH_PRICE_MODE = "d174-uncached-only"` at `touch_policy.py:126`** in the committed file, with
`TOUCH_PRICE_MODES` declared beside it and `price_for_touch` **raising** on an unrecognised mode
instead of falling through to the proxy, which is how a mode could name a corrected price and
deliver the uncorrected one. `touch_price_gpu_s_d174` delegates to
`d162_price.price_gpu_s(TOUCH_UNCACHED_TOKENS, 0, "uncached-only")` rather than re-deriving the
number, because `TOUCH_PRICE_D162` holds the coefficients ROUNDED for reading (0.00018243 against
the gate's 0.0001824312597782467) and the coordinator charges at full precision; two prices that
differ in the ninth decimal are exactly the drift `d162_price`'s gate check exists to catch. That
check is run in the unit proof and **PASSES on both trees**.

**Note for the record, because it was reported the other way:** the default is **ON** in the
committed file. A reading of `TOUCH_PRICE_MODE = "reload-proxy"` with the "nothing changes" comment
is a reading of the **`before/` tree**, which is this study's negative control and must read
exactly that. D187's "held or unproved code defaults OFF" is satisfied by the proof, not by
leaving the fix unreachable, and the proofs are in the same commit.

**Why `d162-warm-hit` is not the corrected mode either.** It carries the intercept:
0.067798 + 0.00018243 x 15 = **0.070534 GPU-s**, which is 25.8x the ruled charge. D174 (1) rules
the intercept out as occupancy rather than work, so the mode had to be a new one.

**The defect was not a magnitude error, it was a split register across one decision.** For every
rung-2-and-above arm `live2_d162_pricing` is True (`arms_v6c5.py:53`, `arms_v6shares.py:74`,
`arms_v6state.py:564-575`), so `coordinator.py:1175-1177` already SPENT
`d162_price.price_gpu_s(15, inflight, "uncached-only")` = 0.00273647 GPU-s on each touch. But the
decision whether to touch at all is taken one step earlier, at `coordinator.py:1161`, where
`should_touch` is handed `budget_ok=self.st.budget.can_spend` and asks it about
`price_for_touch(...)` = the reload proxy, 0.2431 to 0.6714 GPU-s. **The gate planned at a price up
to 245x the price the budget was then charged.** That is the "comparator planning at one price
while charged another" failure CLAUDE.md's citing rules name, and it is invisible to any
arm-versus-arm check because every arm met the same unaudited bar.

### The rung-2 comparison had to be re-attributed before it could be read, and that is the first thing to say

**The control arm did not reproduce its own committed value, so the comparison was not read until
that was explained.** The first pass ran 10 to 19 cells in parallel. On it,
`covex-v6-state-uo-c5attr` gave `639cd15ed38c9da0` / 14,207 on the `before` side against its
committed bar of `9a4be873eb3c5fba` / 14,218, while `covex-v6-base`, `covex-v6-rules` and
`covex-v6-fair-c5attr` all matched their committed bars exactly on both sides.

**The cause is already measured and committed in this repository, and the before-side value is
EXACTLY the known perturbed one.** `d190_rung4_r3_proofs.py:189-203` records, under
`host_load_hazard_measured`: at concurrency 3, `covex-v6-base` `af8befb9420ad86a` / 12,085 matched,
`covex-v6-fair-c5attr` `12e4f73ce0ebd865` / 13,812 matched, and `covex-v6-state-uo-c5attr` gave
**`639cd15ed38c9da0` / 14,207, "MISMATCH against 9a4be873eb3c5fba / 14,218"**; run ALONE it gave
`9a4be873eb3c5fba` / 14,218, "matched exactly". Its own reading: "the rung-2 arm's dry digest is
sensitive to host load and the two other arms' are not, so a concurrent run can move one side of a
comparison and not the other. Consistent with the documented `id(obs)` cache key in
`arms_v6state._queued_behind`, which makes decisions depend on allocation history."

**So the 151 setwise differing decisions the parallel pass showed at rung 2 are NOT attributable to
hit 22.** They are a host-load difference between two cells that happened to sit on opposite sides
of that sensitivity. Reporting them as hit 22's Step 2b count would have been a number in the wrong
register that survives every arithmetic check: it is a real diff of two real logs, and it measures
the scheduler of this box rather than the price of a touch. The rung-2, rung-3 and rung-4 pairs
were therefore rerun **SEQUENTIALLY, AT CONCURRENCY 1**, with the before side, the after side and a
semantic-revert control run one after another on the same quiet host.

**And a second control was added, because concurrency 1 alone cannot separate the price from the
allocation.** The two trees also differ in the TEXT of three files, and a docstring's length can
move an allocation pattern that `id(obs)` then reads. `d209_hit22_negctl.py` runs the AFTER tree
with `price_for_touch` rebound to `touch_price_gpu_s` by value: same bytes, same imports, same
allocation, ONE number changed. If the digest follows the price, the price moved the decisions; if
it does not, the price never did.

### Static audit of the read path, done before the controls and consistent with them

For every rung-2-and-above arm `live2_d162_pricing` is True, verified by building each arm and
asking `d162_price.arm_enables` rather than reading the `kw.setdefault` lines: `covex-v6-state-uo`,
`covex-v6-state-uo-c5attr`, `covex-v6-fair-c5attr` and `covex-v6-cf-pd-c5attr` all report
`d162_pricing True, charge_mode uncached-only`. On that branch `coordinator.py:1175` takes
`_touch_price` from `d162_price` and never from `d["price_gpu_s"]`, so the corrected price reaches
exactly ONE decision in the whole tree: the `budget_ok(price)` call inside `should_touch`. Nothing
else reads it. `Budget.can_spend` is pure (`interface.py:420-426`), so asking it a different
question has no side effect, and the planner does not import `touch_policy` at all beyond
`TOUCH_UNCACHED_TOKENS`.

**AND ON THIS CELL THAT ONE DECISION IS NEVER REACHED: the budget refuses 0 of 2,267 touches at
EITHER price.** Measured on the `before` tree with the same budget asked both questions at the same
instant in the run:

| quantity | value |
|---|---|
| `should_touch` calls (all at the `gpu` tier, guard allowed) | 2,267 |
| refused by the budget at the reload proxy (the old price) | **0** |
| refused by the budget at the ruled D174 price | **0** |
| refusals the correction REMOVES | **0** |
| refusals the correction ADDS | 0 |
| `state_touch_emitted` | 2,267 |

**Provenance of the two zeros, because they did NOT come from a counter.** The coordinator's
`touch_refused_budget` counter is not among the statistics `test_hybrid.dry` hands back, so the
refusal counts here are a DIRECT measurement of the gate itself: the tap calls the run's own
`budget_ok` with each price at the instant the decision is taken. The arm's own
`state_touch_emitted` is 2,267, equal to the number of `should_touch` calls, which is the
independent cross-check that nothing was refused: had the gate bitten, fewer touches would have
been emitted than considered.

That is consistent with D174's own census ("budget refusals are ZERO in every committed v5-rules /
v5-rules-2 cell") and it is the answer to "the budget refusals it removes, counted on a dry cell":
**zero, on this cell, because the budget never binds here.** Under Rule 2 the correct label for the
gate on this cell is **UNEXERCISED**: the mechanism is present, live, correctly priced and
reachable, and no condition in this run reaches it. It is not a negative about the fix, and the fix
is still required, because the cell that motivated D174 (covex-v6-state s4, 620 GPU-s on 1,246
touches, 12,824 refusals) is a cell where the budget DID bind, and a 0.25x-capacity or
longer-budget cell can bind again.

### The price distribution, before and after, paired on identical inputs

OBSERVED inputs, CONSTRUCTED counterfactual column. 2,267 touch decisions on the rung-2 dry s4
cell, every one at the `gpu` tier with belief mass 1.000.

| quantity | min | p10 | p50 | p90 | max | mean | distinct values |
|---|---|---|---|---|---|---|---|
| prefix tokens (the INPUT, which does vary) | 8,313 | 9,337 | 10,361 | 11,385 | 12,409 | 10,408.0 | 5 |
| BEFORE price, reload proxy (GPU-s) | 0.288688 | 0.324249 | 0.359809 | 0.393142 | 0.422778 | 0.360169 | 5 |
| AFTER price, D174 uncached-only (GPU-s) | 0.00273647 | 0.00273647 | 0.00273647 | 0.00273647 | 0.00273647 | 0.00273647 | **1, by construction** |
| intermediate `d162-warm-hit`, NOT the ruled mode (GPU-s) | 0.07053445 | - | - | - | 0.07053445 | 0.07053445 | 1 |
| overcharge ratio, reload proxy over ruled | 105.50 | 118.49 | 131.49 | 143.67 | 154.50 | 131.62 | 5 |

**The spread in the BEFORE column is the defect, not noise**: it has exactly 5 distinct values
because the prefix has exactly 5, which is the wrong-shape error made visible. The AFTER column is
a constant, and per consistency check 3 a constant where a distribution is expected is normally the
alarm; here it IS the specification (a warm touch does not re-materialise the prefix), and the
quantity that must still carry a distribution is the prefix length, reported above to show the
inputs did vary.

**The overcharge on this cell's real prefixes is 105x to 155x, not 3.6x to 9.8x.** The module's own
3.6x to 9.8x is against the intermediate `d162-warm-hit` price, which carries the intercept D174 (1)
excludes; the intercept is 96.1 percent of that number. Anyone carrying "3.6x to 9.8x" forward
understates the correction by a factor of about 26.

### Step 2b, per hit, with the attribution that makes the counts mean something

Two registers are reported for every pair, because they are not the same claim. **COMMITTED KEY**
is `test_hybrid._decision_key` (period, action kind, opportunities acted on, representation,
defer) as a multiset difference, which is the register the committed D205 step-2b numbers are in.
**WHOLE ROW** is a stricter diff that also counts a changed `note` or `piece_tokens`. **POSITIONAL**
is reported and must not be read as a magnitude: `test_hybrid._differing`'s own docstring warns it
saturates once an early divergence desynchronises the rest.

| pair | what it isolates | rows | COMMITTED KEY | WHOLE ROW | positional |
|---|---|---|---|---|---|
| `after_no22` vs `after`, rung 2 | **HIT 22 ALONE** | 14,218 vs 14,218 | **0** | **0** | **0** |
| `before` vs `after_no22`, rung 2 | **HITS 26 + 6 ALONE** | 14,207 vs 14,218 | 85 | 151 | 6,849 |
| `before` vs `after`, rung 2 | all three together | 14,207 vs 14,218 | 85 | 151 | 6,849 |
| `before` vs `after`, rung 3 | all three together | 13,812 vs 13,812 | **0** | **0** | **0** |

**Read the first two rows together, because together they say something neither says alone.**

**HIT 22 MOVES ZERO DECISIONS on this cell, byte-identically**, and that is now a MEASUREMENT on a
pair of trees differing in nothing but the touch price, not an inference from the read audit. It
agrees exactly with the audit (one read, never reached: 0 of 2,267 refusals at either price) and
with the paired price cells, which found the SAME 2,267 touch decisions over the SAME five-valued
prefix distribution in both trees.

**HITS 26 AND 6 MOVE 85 COMMITTED-KEY DECISIONS, AND THEY CANNOT POSSIBLY HAVE DONE SO
SEMANTICALLY.** Hit 26's only functional surface returns `None` on both sides for every input, and
hit 6's module `adapter` is not imported at all on the dry path. What changed in those two files
on the dry path is COMMENTS, DOCSTRINGS AND ONE UNREACHED STRING. So:

> **Editing only comments and docstrings in `engine_actions.py` moves the rung-2 arm's dry decision
> log by 85 committed-key decisions and 11 rows.**

That is a quantified demonstration of the `id(obs)` cache-key defect
(`arms_v6state.V6StateArm._queued_behind` keys its pending-work cache on a MEMORY ADDRESS, so
decisions depend on allocation history), and it is corroborated by the repo's own committed
measurement of the same arm: `d190_rung4_r3_proofs.py:189-203` has `covex-v6-state-uo-c5attr` at
`639cd15ed38c9da0` / 14,207 under concurrency and `9a4be873eb3c5fba` / 14,218 alone, with
`covex-v6-base` and `covex-v6-fair-c5attr` insensitive in both settings. In my runs the value is
TREE-determined rather than load-determined (`before` gave `639cd15ed38c9da0` / 14,207 in THREE
independent processes, and `after` and `after_no22` gave `9a4be873eb3c5fba` / 14,218 in three more,
all at `/proc/loadavg` 1-minute values between 10.65 and 25.46), which points at allocation layout rather than
scheduling, but both are the same defect and I do not need to choose between them to report it.

**THE CONSEQUENCE FOR THE FINAL LADDER, and it is the most useful thing in this report for whoever
builds it: UNTIL THE `id(obs)` FIX IS ON, A RUNG-2 DRY DIGEST IS NOT A PROPERTY OF THE CODE.** It
cannot serve as a byte-identity bar, it cannot serve as a Step 2b baseline, and a comment change
will break it. D208 (2) already folds that fix into the final ladder, which is exactly where it
needs to be; what this adds is that the rung-2 bar should not be quoted for ANY comparison taken on
a tree that is not byte-identical in every module the arm imports.

### Negative control for hit 22

Three controls, in increasing strength.

1. **The `before` tree.** The same recipe, the same cell, the fix absent: price 0.2887 to 0.4228
   GPU-s, `TOUCH_PRICE_MODE` `"reload-proxy"`, `d162-warm-hit` unreachable. Collapses to the old
   behaviour by construction.
2. **The paired budget verdicts.** The same budget asked about the old price at the same instant:
   0 of 2,267 refusals, so disabling the fix changes no admission on this cell.
3. **The semantic revert, `d209_hit22_negctl.py`.** The AFTER tree with `price_for_touch` rebound
   to `touch_price_gpu_s` by value: same bytes, same imports, same allocation, one number changed.
   **RESULT: `9a4be873eb3c5fba` / 14,218, IDENTICAL to the unreverted AFTER tree.
   THE DIGEST DOES NOT FOLLOW THE PRICE, so the price never moved the decisions.**

**And the fourth control closes it: with the `id(obs)` defect disabled, every tree agrees, and they
agree ON THE COMMITTED BAR.** `cf_pd_one_cell.py --diag-epoch-cache-key` forces the pending-work
cache to rebuild once per decision period, which is what the key was meant to do:

| rung-2 variant, dry s4, committed recipe | digest / rows |
|---|---|
| `before` (origin code), cache key as committed | `639cd15ed38c9da0` / 14,207 |
| `after` (all three fixes) | `9a4be873eb3c5fba` / 14,218 |
| `after_no22` (hits 26 and 6 only, `touch_policy.py` byte-identical) | `9a4be873eb3c5fba` / 14,218 |
| `after` with the price SEMANTICALLY REVERTED (same bytes, one value) | `9a4be873eb3c5fba` / 14,218 |
| `before` with `--diag-epoch-cache-key` | **`9a4be873eb3c5fba` / 14,218** |
| `after` with `--diag-epoch-cache-key` | **`9a4be873eb3c5fba` / 14,218** |
| COMMITTED BAR (EXPERIMENTS.md StudyFROZEN-test; `d190_rung4_r3_proofs.py` "alone") | `9a4be873eb3c5fba` / 14,218 |

**Five of the six runs, and the committed bar, give the same digest. The single outlier is the one
tree with the `id(obs)` cache key live and no fix to perturb it, and its value `639cd15ed38c9da0` /
14,207 is EXACTLY the value the committed proof recorded for the same arm under concurrency.** With
the cache key fixed, both trees reproduce the committed bar even at loadavg 19 to 25, so the defect
is the cache key and nothing else: not load as such, not the price, not the comments.

### Step 3 trace, one touch decision, readable by hand

```
rung 2 covex-v6-state-uo-c5attr, dry s4, posted knobs; one of 2,267 identical-shaped decisions
INPUTS   session robo001|s001, belief {gpu: 1.0, host: 0.0, cold: 0.0}, prefix_tokens 9,337
GUARD    mixed_touch_guard -> allowed, "wholly gpu at belief 1.000"   (PURE_TIER_MIN_BELIEF 0.95)
PRICE    BEFORE  touch_price_gpu_s(9337, gpu) = costs.recall_gpu_s(9337, "GPU-WARM") = 0.3242485
         AFTER   d162_price.price_gpu_s(15, 0, "uncached-only")
                 = 0.0001824312597782467 x 15                        = 0.0027365
         ratio 118.5x                                      (d162-warm-hit would be 0.0705344)
BUDGET   can_spend(0.3242485) -> True        can_spend(0.0027365) -> True
         so the gate does not bind at either price: NOT the decision that moved
CHARGE   coordinator.py:1175, d162_pricing True for this arm:
         spend(d162_price.price_gpu_s(15, uncached_in_flight, "uncached-only")) = 0.0027365
         UNCHANGED by this fix, which is the point: the charge was already the ruled one and the
         GATE was not
SHARES   _share_ok(qtype=robot, uncached=15, kind=touch) -> admitted within the recall floor
OUTCOME  touch issued; counts touch_issued_gpu += 1; state_touch_emitted 2,267 in both trees
WHICH BUDGET BOUND IT: neither. KV capacity is not enforced on a dry cell and the GPU budget never
refused a touch at either price.
```

## HIT 6, `live/adapter.py:137-144`: the policy, the key, and the part that does not reach live2

**The required behaviour, implemented (D209 (2)).** A failed fetch never substitutes 0.0. The
field is MARKED MISSING (`fm_kv_missing`, `fm_kv_state`); the decision uses the LAST GOOD VALUE at
most `LAST_GOOD_MAX_AGE_S = 1.0 s` old; otherwise capacity is UNKNOWN AND CONSERVATIVE at
`KV_UNKNOWN_CONSERVATIVE = 1.0`, the MAXIMUM of [0, 1]; the cell RECORDS THE COUNT, split by which
branch it took; and `metrics_health()` returns `metrics_degraded`, the cell flag, true for any run
in which a fetch failed or a KV key was absent.

**Why 1.0 is the conservative end, checked at each read site rather than assumed.**
`preble_adapted.py:57` and `constructed.py:416` take `max(gpu_kv_fraction, queue_term)`, so 1.0 is
the pressure end; `arms_v6cf.py:306` computes a free-KV estimate from `1 - frac`, so 1.0 gives
zero free pool; `uniscale_adapted.py:63` uses it as a raw feature, where 1.0 is the top of the
range the coefficient was fitted over. An unknown is never permissive, in either direction.

**How it relates to the counter another session committed at `29742254`.** It is BUILT ON, not
reverted. `metrics_failures` keeps its two existing field names `n` and `last` with their existing
meanings, so any existing reader is unaffected, and five fields are added beside them:
`n_served_last_good`, `n_served_unknown`, `n_kv_key_missing`, `n_kv_key_aliased` and
`kv_key_seen`. That commit's docstring said the fallback value was deliberately unchanged because
a ruling was owed; D209 (2) is that ruling, and this is the behaviour change it authorises.

**AND THE KEY NAME WAS ALSO WRONG, so a SUCCESSFUL scrape read 0.0 too.** This engine emits
`vllm:kv_cache_usage_perc` (0.7215 at capture) and no `vllm:gpu_cache_usage_perc`. Both spellings
are now accepted and the value is republished under the OLD name, which repairs every reader
without editing a file this session does not own. Two in-repo witnesses already use the current
spelling (`experiments/cost/study_r5_fleet.py`, `experiments/cost/study_x_vllm.py`), and
`live/fake_server.py` still emits the old one, which is why both are accepted rather than one
being replaced. A scrape carrying NEITHER name is treated as missing and takes the same policy,
because defaulting it would reach the same 0.0 by a different road. The pre-first-poll value in
`start_poller` was also `{}` and is now the conservative unknown: that was a second route to 0.0,
reachable by any decision taken inside the first poll interval, and it would have survived a fix
that touched only the exception path.

**Trace, five states, one line each, from the unit proof (no server contacted: `urlopen` is
stubbed with verbatim lines from the committed scrape).** `kv` is what a reader's
`m.get("vllm:gpu_cache_usage_perc", 0.0)` actually receives.

| state | BEFORE (control) | AFTER | marking | counters after the step |
|---|---|---|---|---|
| 1 scrape with the engine's CURRENT key, `vllm:kv_cache_usage_perc` 0.7215 | **kv = 0.0** | kv = 0.7215447154471545 | observed, source key `vllm:kv_cache_usage_perc` | aliased 1 |
| 2 scrape with the OLDER key (`fake_server`), 0.4242 | kv = 0.4242 | kv = 0.4242 | observed, source key `vllm:gpu_cache_usage_perc` | unchanged |
| 3 fetch RAISES, 0 s after a good value | **kv = 0.0** | kv = 0.4242 | `last_good`, age 0.0 s | failures n=1, served_last_good 1 |
| 4 fetch RAISES again, 1.2 s after the last good value | **kv = 0.0** | kv = 1.0 | `unknown_conservative`, age 1.2014 s | failures n=2, served_unknown 1 |
| 5 scrape SUCCEEDS carrying NEITHER key | **kv = 0.0** | kv = 1.0 | `unknown_conservative` | kv_key_missing 1, served_unknown 2 |

`metrics_health()` after the five states: `metrics_degraded: true`, with the full counter block and
the policy string. The BEFORE column is the Step 4 negative control, measured rather than
asserted: with the fix absent, four of the five states hand a reader the permissive minimum.

**AND NOW THE PART THE BRIEF, THE TRIAGE AND THE VERIFIED READ CENSUS ALL MISS, which is the real
blast-radius answer.** The read census is correct about the five read sites and about which modules
read the field. It cannot see what the mapping CONTAINS at run time, and the answer is nothing:

- `st.metrics` has exactly ONE writer in the tree, `coordinator.py:489`,
  `self.st.metrics = self.be.metrics()`, and it is skipped entirely on a dry cell
  (`if not self.dry_run and self.be is not None`).
- In every reported live2 cell `be` is `AsyncLive2Backend`. `run_live2_real.py:476` and
  `procsplit.py:312` are the only two constructions on the cell path, and `run_live2_real.py:422`
  is the only writer of `cell.json` in the tree, so the committed graded cells are exactly these.
- **`AsyncLive2Backend` is not an `HttpBackend` subclass, contains no `/metrics` string, and its
  `metrics()` returns its OWN build and wire statistics** (`n_built`, `wire_extra_delay_ms`,
  `submit_delay_total_ms`, `cache`, ...). There is no `vllm:` key in it at any time.
- `start_poller`, which is the only thing that would make `adapter`'s scrape run in a loop, has
  exactly one caller in the tree: `live/run_live_cell.py:91`, the StudyLIVE1 v1 harness.
- `Live2Backend`, the `HttpBackend` subclass the triage's S2 identified, IS reached from
  `run_live2_cell.py`, `scale_smoke.py`, `harness_checks.py`, `study_live2_pilot.py` and five
  tests, and none of those writes a graded `cell.json`.

**So `cloud.gpu_kv_fraction` is 0.0 in every reported live2 cell not because a fetch failed and not
because a key was renamed, but because live2 never scrapes /metrics at all.** Correcting the key in
`cstate.py:663` alone would leave the gate at 0.0 for ever while looking like a fix, which is the
same trap as fixing only the exception path. This fix is therefore correct and complete for the v1
`live/` path and reaches **ZERO** reported live2 cells.

**Consequences, stated so the calibration the coordinator asked for holds.** The expectation that
`preble`, `b9` and `uniscale` SHOULD move was based on the read census, and those three have since
been ruled OUT of the reported baseline set, so the expectation is moot twice over. On a DRY cell
they cannot move anyway,
because a dry cell never calls `be.metrics()` and never imports `adapter` (measured:
`"adapter" in sys.modules` is False after importing `test_hybrid` and registering every v6 module).
Their digests being identical here is therefore the expected result and not a sign the fix missed
them. What a live cell of those arms did is a separate question that only the live2 half can
answer.

## ESCALATIONS

**E1. The live2 half of hit 6 needs `asyncbackend.py`, which this session does not own.** The exact
change: give `AsyncLive2Backend` a `/metrics` scrape with the same missing-value policy as
`HttpBackend` (accept both key spellings, republish under the canonical one, mark missing, last
good within 1 s, else conservative 1.0, count, expose `metrics_health()`), and have
`coordinator.py:489` keep assigning `be.metrics()` unchanged. Without it, every live2 KV-pressure
read stays at the permissive minimum whatever `cstate.py` calls the key.

**E2. `cstate.py` was deliberately NOT edited, and I am saying so rather than stalling.** I was
told the H100 reports the user has given me `cstate.py`, and I did not act on an agent's report of
a ruling. But the stronger reason is substantive and would apply either way: the change worth
making there is not a key rename (the key is absent whatever its name, per E1), and pushing the
never-0.0 policy into `cstate.py:663` WOULD change every DRY digest of the four arms that read the
field, including rung 4, because a dry cell's `metrics` is `{}` and the policy would hand it the
conservative 1.0 instead of 0.0. That is a methodological change to the dry regime, it collides
with the final-ladder build in flight, and triage hit 5 (`cstate.py:278`, metrics empty in dry
cells) is still unruled. **Proposed replacement text for the two misleading doc lines**, which are
wrong twice over and should be corrected whoever does it:

- `live2/cstate.py:17`: `| `cloud.gpu_kv_fraction` | the server's KV-usage gauge. NOT CONNECTED on
  the live2 path: the only writer of `metrics` is `coordinator.py:489 = be.metrics()`, and
  `AsyncLive2Backend.metrics()` returns build and wire statistics with no `vllm:` key, so this
  field reads its 0.0 default in every cell. D209 (2) escalation E1. |`
- `live2/arms_v6cf.py:283`: the docstring's `vllm:gpu_cache_usage_perc` should read
  `vllm:kv_cache_usage_perc (vLLM 0.31.0; the gauge was renamed)` and should carry the same
  not-connected note.

**E3. The cell flag cannot be written from a file this session owns.** `metrics_health()` is
exposed on the backend, but `cell.json` is assembled from a fixed key list at
`run_live2_real.py:383-422`. One line is needed there,
`out["metrics_health"] = (res.get("backend") or {}).get("metrics_health")`, together with E1
putting it into `be.metrics()`. Until then the flag exists and nothing writes it to the cell.

**E4. A separate ABSENT-MECHANISM finding, found while scoping hit 6 and reported rather than
fixed.** `engine_actions.hold_back` (`:276`) is **dead code**: its only two occurrences in the tree
are its own definition and a docstring mention at `:21`, and no module calls it. Its own docstring
says it is "the one D150 calls 'above all'" - refusing a large cold rebuild that would evict a
history whose question is due. So the lever D150 ranks first is defined, documented, instrumented
in prose, and never invoked. This is the `desired_tier` shape again and belongs in the dead-channel
catalogue beside it.

**E5. D209 (1) parity: the four `-rr` seed verdicts now sit on superseded code, and nobody should
read them as current.** Hit 22 moves the rung-3 decision digest off `12e4f73ce0ebd865` / 13,812,
which is the bar `covex-v6-fair-c5attr-rr` s4 to s7 were judged against (D208 (1)). Those four
verdicts were correct on the code of their day and are now **SUPERSEDED**, exactly as D209 (1)
specifies for an implementation correction that changes decisions. The final ladder is the rerun
that restates them.


**E6. D211 signal (a)'s primary input is an empty field, and one line would fill it.**
`belief.gpu_tokens_by_session` (`schema.py:316`) is logged on every decision row and is `{}` on all
16,840 rows of the committed rung-3 cell, because its only producer, `arms_policy.py:1067-1075`, is
never entered by the reported ladder. Needed: populate it from cstate's own session records where
the decision row is built, so signal (a) becomes a join on recorded data instead of a
reconstruction. Not this session's file.

**E7. D211 validation needs a counter series that no committed cell carries, and the capture defect
has two halves.** `study_frozen_grid_driver_v25.sh:39` selects a fixed five series and ALSO does
`sed 's/{[^}]*}//'` then `awk '{a[$1]+=$2}'`, so it strips labels and sums by bare key: adding
`prompt_tokens_by_source_total` to the regex alone would have collapsed `local_compute`,
`local_cache_hit` and `external_kv_transfer` into one number and left the host share unrecoverable.
This session diagnosed both halves from the driver source; the H100 has since fixed it forward in
driver v32 (`31561256`) keeping the labels, which closes it prospectively and not retrospectively.

**E8. OPERATIONAL, and the one that needs a decision today rather than a file.** Two sessions ran
dry proof cells on flash concurrently at `/proc/loadavg` up to 25.46, and the rung-2-class dry
digest is measurably sensitive to exactly that. See the OPERATIONAL FINDING section below.

## The touch-price flip in isolation on a state-planner arm, asked for separately and already here

The pair that isolates the flip is `after_no22` against `after`: two trees whose only difference is
`touch_policy.py`, on `covex-v6-state-uo-c5attr`, a state-planner arm, at the committed recipe. It
was costed elsewhere as a separate 1,200 s run; it falls out of the three-tree design for free.

| quantity | `after_no22` (old price) | `after` (ruled price) | direction and size |
|---|---|---|---|
| decision log digest / rows | `9a4be873eb3c5fba` / 14,218 | `9a4be873eb3c5fba` / 14,218 | **identical, 0 decisions differ in either register, 0 positional** |
| state decisions | 60,934 | 60,934 | **unchanged**, and it is 60,934 in every one of the six rung-2 runs in this study, including the two `before` ones. The 85 differing decisions are RELEASE decisions, not a different number of state decisions. |
| touch decisions considered | 2,267 | 2,267 | unchanged |
| touches issued (`state_touch_emitted`) | 2,267 | 2,267 | unchanged |
| touch prices that move | n/a | **2,267 of 2,267** | **ALL DOWNWARD**, from a 5-valued distribution over 0.288688 to 0.422778 GPU-s to the constant 0.00273647 GPU-s: a factor of 105.50x at the smallest prefix to 154.50x at the largest |
| budget verdicts that flip | 0 of 2,267 | 0 of 2,267 | **none**, because the budget refuses at neither price on this cell |
| budget GPU-seconds actually spent per touch | 0.00273647 | 0.00273647 | **unchanged**, because `coordinator.py:1175` already charged the ruled price for this arm |

**So the direction is unambiguous and the magnitude is large, and no decision follows it.** Every
one of the 2,267 prices falls by two orders of magnitude; the quantity those prices were feeding,
the `should_touch` budget gate, had slack at both values on this cell; and the quantity the budget
actually spends was already correct. That is the whole of hit 22 in one table: a REAL and large
correction to a number, on a cell where the number was not binding.

### D211 step 2, in the only form committed data allows, and the number is striking

Signal (a) as ruled is `max(0, cached_tokens - gpu_prefix_believed)` and **cannot be computed**: the
belief's GPU prefix in tokens is not recorded for any reported arm, confirmed by count over the
whole log, `decision_rows_with_nonempty_gpu_tokens_by_session = 0` of 16,840. What CAN be computed
exactly, with no reconstruction and no proxy, is the two directions of belief error, by joining the
committed per-request usage to the committed residency log on session and submission time.
Committed rung-3 cell `covex-v6-fair-c5attr-rr_n16_s4_1200s_h27_3t_L3_epg_rq30` at `d796f2d5`:

| quantity | value | denominator |
|---|---|---|
| requests in the cell | 12,221 | |
| requests joinable to a belief (a session-bearing request; a dashcam monitor has no session) | 2,920 | **coverage 23.89 percent, reported because it bounds everything below** |
| **BELIEF TOO OPTIMISTIC**: believed `gpu` at submission, engine reused 0 prompt tokens | **3** | of 2,904 believed-gpu requests, **0.10 percent** |
| **RESIDENCY THE BELIEF CANNOT SEE**: believed `cold` at submission, engine reused more than 0 | **16** | of 16 believed-cold requests, **100 percent** |
| cached tokens when that happens | min 992, p25 992, **p50 4,048**, p75 11,616, max 13,776, mean 5,485 | 10 distinct values over 16 requests |

**Read in the direction D211 cares about: the belief is almost never over-optimistic (0.10 percent),
and when it says COLD it is wrong EVERY TIME, by a median of 4,048 reused tokens and up to 13,776.**
That is the shape D211 predicted: reload is happening and the policy prices it as a cold rebuild.

**Three limits on it, stated with it rather than under it.** (i) **n = 16.** Sixteen believed-cold
submissions in a 12,221-request cell is a tiny stratum, so 16 of 16 is directionally strong and
numerically underpowered, and it is not a rate to quote without that denominator. (ii) It is an
**UPPER BOUND on unobserved HOST residency, not a measurement of it**: this engine cannot separate a
GPU hit from a host hit per request, which is the whole of hit 26, so some of those 16 may be GPU
hits the belief had written off rather than host reloads. (iii) **UNVALIDATED**, and unvalidatable
on this cell: the pre-registered agreement bar needs the aggregate host counter, which no committed
cell carries. It therefore changes no belief, no price and no verdict here, and the frozen bar is
untouched.

## Rule 2 classification, per hit, stated once and plainly

| hit | did the mechanism operate? | did a decision move? | classification |
|---|---|---|---|
| 22, touch price | YES. The gate is live, reachable, and now reads the ruled charge. Its one read is `budget_ok(price)` in `should_touch`, verified by audit and by the arm-level switch probe. | **NO, byte-identically, on the dry s4 cell** | **INCONCLUSIVE / UNEXERCISED.** The budget refuses 0 of 2,267 touches at EITHER price on this cell, so no condition in the run reaches the decision the switch changes. It is NOT "fired and did not help", and it is NOT a negative about the fix. |
| 26, engine key register | The per-request host channel does not exist on this engine, by measurement. | **NO**, and it could not: the function returns `None` on both sides for every input. | **ABSENT LINK** in Step 2b's sense for the decision count, with the real result being a STRUCTURAL finding: a per-request host belief is not achievable on vLLM 0.31.0, so RELOAD is **UNEXERCISED for a structural reason**. |
| 6, metrics missing value | YES on the v1 `live/` path, demonstrated over the whole five-state space. | **NO on a dry cell**, and it cannot: `adapter` is not imported on the dry path at all (measured). | **ABSENT LINK on the dry cell**, by construction and not by a null. On a LIVE cell the mechanism is live for the v1 path and **ABSENT for live2**, because live2's backend scrapes no /metrics (escalation E1). |

**Why none of this is reported as "the fixes do nothing".** Two of the three were never going to move
a dry decision and that was established in Step 0 BEFORE the sweep, not discovered in a null. The
third is a gate that now reads the right number on a cell where no gate binds; the cell that
motivated D174 is one where it did bind (620 GPU-s over 1,246 touches, 12,824 refusals), and a
0.25x-capacity or tighter-budget cell can bind again. **A correction that is only visible when the
budget binds is still a correction, and shipping it unproved-but-on would have been the error in
the other direction.**

## The default IS flipped, and the line number, because this has now been reported wrong twice

Two parallel sessions have reported that `TOUCH_PRICE_MODE` is still `"reload-proxy"` with the
comment "DEFAULT, the committed behaviour; nothing changes". That line is at
`touch_policy.py:108` in the **`before/` tree and at `origin/main`**, which is this study's
negative control and must read exactly that. In the file this commit ships it is
**`touch_policy.py:126`, `TOUCH_PRICE_MODE = "d174-uncached-only"`**, with
`TOUCH_PRICE_MODES` beside it and `price_for_touch` raising on an unknown mode. The flip is ON, the
proofs are in the same commit, and D187's "held or unproved code defaults OFF" is satisfied by the
proof rather than by leaving the fix unreachable.

**And the premise that went with it is now measured false and should not propagate.** The H100
handoff records, at 15:30, "The touch-price fix MOVES rung 3/4 digests by design; do not reuse
`12e4f73ce0ebd865` / 13,812 as the final ladder's bar." The first clause is **wrong**: hit 22 alone
is byte-identical at rung 2 (0 decisions, 0 rows) and rung 3 is identical on both sides of the
full three-fix pair. The second clause is **right, for a different and more important reason**: the
rung-3 bar should not be reused because the rung-2-class dry digest is allocation- and
load-sensitive until the `id(obs)` fix lands, not because the touch price moved it.

## OPERATIONAL FINDING, and it needs acting on today rather than filing

**Two sessions are running dry proof cells on flash at the same time, flash reached loadavg 25.5,
and the rung-2-class dry digest is measurably sensitive to exactly that.** The committed proof that
established the sensitivity (`d190_rung4_r3_proofs.py:189-203`) states its own remedy in its first
line: "why every cell here runs ALONE". Neither this session's sweep (10 concurrent cells, nice 5)
nor the final-ladder session's proof cells observed that, and both were running interleaved: this
session's `ps` shows `cf_pd_one_cell.py ... --rows-out .../d208_deliverables/.../ladder_final/cells/`
alongside its own. **Any rung-2-class digest either session produced under that load is suspect, in
both directions.** This session's own numbers were therefore re-derived from a pair that cannot be
affected by load (the same tree differing only in the touch price), and the rung-2 pair was
re-queued at concurrency 1.

The 2026-11-23 15:28 user ruling on proof load ("nice 19, at most two proof processes, never across
a run boundary, host load logged") is written for the H100, where live measured cells run. **The
measured hazard on flash is of the same kind and the ruling does not reach it**, because flash runs
no live cells and the thing being perturbed is another session's DRY digest. Recommended, for the
user to rule: the ALONE rule applies to every rung-2-class dry proof cell on any box, and flash
coordinates proof-cell slots the way the H100 coordinates them against run boundaries. Recorded
with its magnitude, as asked: this session's cells ran at `/proc/loadavg` 1-minute values of 10.65
to 25.46, well above the 9.00 ceiling the committed record documents.

**A queued confirmatory run that someone may want to stop, disclosed rather than left to surprise
anyone.** A concurrency-1 chain (`alone_chain.sh`, pids 180047 and 180050 at the time of writing)
is waiting for this session's sweeps to go quiet and will then run seven more dry cells
sequentially, about 25 minutes. It was queued when the rung-2 move was still believed to be a
concurrency artefact; the `--diag-epoch-cache-key` triple and the same-tree semantic revert have
since settled the attribution without it, so its output is **confirmatory only** and nothing in
this report depends on it. If flash should be quiet for the final-ladder build, stopping those pids
costs nothing. This session could not stop them itself: the sandbox declined the `kill`, which is
why they are named here instead.

## D211, host residency: pre-registered and frozen, and the two things that block it

**Step 1 DONE.** `results/orchestration/live2/placeholder_fixes/d211_host_attribution_prereg.json`,
frozen at **sha256 `f1c8d8ebdd3671e242ac5cbf0e55d0b7be2b0b446a6a3017f86bbc8a2bae0025`** (the file
with its own `frozen_by` field removed, `json.dumps(sort_keys=True, separators=(",",":"))`). The
user's proposed bar is frozen EXACTLY as proposed, 20 percent per 10 s window in at least 80 percent
of host-active windows plus 10 percent over the run; two objections are recorded beside it as
**arguments made before freezing and NOT APPLIED**, so the bar cannot later be said to have moved.
It is a SEPARATE pre-registration and does not touch the StudyLADDER-FINAL freeze
(`sha256 d6d8b6c1...`). The three H100 windowing caveats that arrived after the freeze are in
`d211_host_attribution_prereg_addendum.json`, deliberately NOT edited into the frozen file.

**Step 2 NOT DONE, and the reason is a finding rather than a delay.** Signal (a) needs
`cached_tokens` (present per request, confirmed) AND the belief's predicted GPU-resident prefix IN
TOKENS at submission. That second input **is not recorded for any reported arm**: the schema field
exists (`schema.py:316`, `belief.gpu_tokens_by_session`), it is logged on every decision row, and it
is **EMPTY ON ALL 16,840 ROWS** of the committed rung-3 live cell, including all 2,667
`state_action` rows. Its only producer is `arms_policy.py:1067-1075`, and the reported ladder never
enters `arms_policy.py` (the triage's structural fact S1). So it is `{}` by construction for every
arm we report: **a declared, typed, logged channel that no reported arm fills, and it is the one
input D211's primary signal needs.** It could be reconstructed by accumulating
`release_piece.piece_tokens` per session and resetting on an EVICT, but that is a declared proxy
with nothing to validate it against, because the counter series does not exist for committed cells
either, and check 6 forbids a questionable proxy in a headline when the proxy IS the headline.
**The fix is one line where the decision row is built: populate `belief.gpu_tokens_by_session` from
cstate's own session records.** After that, signal (a) is a join on recorded data. That file is not
this session's, so it is escalated with the field named (E6).

**Steps 3 and 4 BLOCKED on committed data, prospectively unblocked.** No committed cell carries any
aggregate host series: the capture is a fixed five-series grep at
`study_frozen_grid_driver_v25.sh:39` which also strips labels and sums by bare key, so
`prompt_tokens_by_source_total` could not have been recovered even if the regex had matched. This
session diagnosed that from the driver source and the H100 has since fixed it forward in driver v32
(`31561256`, labels kept). Validation is therefore possible only on cells recorded from the v32
handover onward, which is inside D211's own deadline ("before any 0.25x policy cell").

**Step 5 NOT DONE, and shipping it would have changed nothing.** The belief change and host-warm
pricing must ship with the D211 fallback as the DEFAULT until the bar is met on real data, so the
shipped behaviour is identical either way. Building it now would add an unproved policy path to the
commit the final ladder is about to be built on, for zero behavioural gain. It is specified instead:
the belief gains a `host` branch fed by whichever signal passes, and `touch_policy.build_price_gpu_s`
and `price_for_touch` price `host` at the committed M3 / ENG1b reload cost (about 0.12 s per 8k
tokens) rather than at the cold rate, which both functions already have a branch for
(`READINESS["host"] = "HOST-WARM"`).

**FINAL_LADDER_CELLS NOT POSTED.** It is a queue line in `research/OVERNIGHT_HANDOFF_H100.md`, which
is a `research/*.md` file this session does not own, and the three final arms
(`covex-v6-state-final`, `covex-v6-fair-final`, `covex-v6-final`) are the parallel session's build
and are not in the registry this session measured. Posting cells for arms this session cannot
verify exist would be the wrong register. The s4 order to use when it is posted is the ruled one:
`covex-v6-fair-final`, then `covex-v6-final`, then `covex-v6-state-final`.

## Proposed row text, for the owner of `research/*.md`

**`research/EXPERIMENTS.md`, new row** (E-id PROPOSED, not set by this session):

> | StudyPLACEHOLDER-FIX | orchestration | D209 (2): fix hits 22, 26 and 6 and prove each one's effect separately, before the final ladder is built. | `experiments/orchestration/live2/d209_{digest_driver,unit_proofs,hit22_prices,step2b_rowdiff,negctl,assemble}.py` | two (for attribution three) `git archive` trees at one literal origin sha; the committed `cf_pd_one_cell.py --cutoff-off` recipe | `results/orchestration/live2/placeholder_fixes/d209_placeholder_fix_proofs.json`, `reports/study_d209_placeholder_fixes.md` | flash (CPU, dry cells) | 23 arms x 2 trees + a 7-arm attribution pass + 5 unit-proof states | **ALL THREE FIXED; NONE MOVES A DRY DECISION, AND THE REASONS DIFFER AND ARE THE RESULT.** Hit 22's mode is flipped to the D174 uncached-only charge and is byte-identical at rung 2 (0 decisions): the budget refuses 0 of 2,267 touches at either price, so the gate is UNEXERCISED on this cell, while the price it reads was 105x to 155x too high and WRONG-SHAPED. Hit 26: the probe shows host residency real (26 % of prompt tokens) and NOT observable per request, so RELOAD is UNEXERCISED STRUCTURALLY; no key invented. Hit 6: both the renamed key (`vllm:kv_cache_usage_perc`) and the never-0.0 policy are in, and the fix reaches ZERO live2 cells because `AsyncLive2Backend` scrapes no /metrics. **INCIDENTAL AND LARGER THAN ANY OF THEM: a COMMENT-ONLY edit to `engine_actions.py` moves the rung-2 arm's dry log by 85 committed-key decisions and 11 rows, so a rung-2 dry digest is not a property of the code until the `id(obs)` fix is on.** | E-id PROPOSED | checks 1-7 run; check 1 FAILED FIRST on the control and that drove the method | Step 2b per hit with per-hit attribution; negative control per hit; hit 22 also controlled by a same-tree semantic revert | base, rules and every reported baseline byte-identical |

**`results/INDEX.md`, new rows**:

> | `results/orchestration/live2/placeholder_fixes/d209_placeholder_fix_proofs.json` | `d209_digest_driver.py` + 4 | n/a | flash CPU | 23 arms x 2 trees, seed 4 | all three D209 (2) fixes in; 0 dry decisions moved by any of them; a comment-only edit moves rung 2 by 85 | new |
> | `results/orchestration/live2/placeholder_fixes/d211_host_attribution_prereg.json` | frozen pre-registration | n/a | flash | n/a | D211 bar frozen at sha256 `f1c8d8eb...`; validation impossible on committed cells | new |

**`research/STATUS.md`**: last-updated line to 2026-11-23 (later), noting that D209 (2) is committed,
that no dry decision moved and why, that the rung-2 dry digest is allocation-sensitive so the
final ladder must carry the `id(obs)` fix for its bars to mean anything, and that D211 is frozen but
unvalidatable on committed data.
