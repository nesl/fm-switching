# StudyFIG1-motivation: the paper's motivation figures M1-M6

Engineering / plotting task, user-authorized (prompt of 2026-11-18). No GPU, no model,
no new measurement. HEAD at start `4e6de56` (after `git pull --ff-only`). Every plotted
and annotated number is reproduced from a committed result file and cross-checked
against its source report; the per-figure `figures/motivation/figM*.json` records, for
each number, its source file, the computation, n, the matching report value and the
ratio this run / report. Scripts live in `plots/motivation/`; outputs (PDF vector +
300 dpi PNG) in `figures/motivation/`. No em dashes anywhere; every figure checked for
Type-3 fonts (none) and TrueType embedding (present).

**Revision 1 (2026-11-18).** M4 was redone around the three readiness tiers of the
problem setting (GPU-warm / host / cold), with disk removed (not a tier yet; D78, Q12);
see the M4 section. Small fixes: M1 panel letters moved off the bars and the caption now
frames it as device vs cloud (bigger model plus full history) and adds the history-only
contrast (+17.5 pp, same 32B, StudyR1 K1 minus K3 on outside-window questions); M2's
"cold 11k rebuild" label moved inside the shaded band clear of the legend, and its
caption notes that its 44.9 s (ENG1d P40) and M4's 36.5 s cold value (ENG1c P40) come
from different studies; M3a uses plain-number y ticks (3, 6, 10, 20); M3b adds "idle"
(white) to the legend, labels the one-go row's first idle gap "image preprocessing
(engine idle)", and the caption explains the pink (both) steps after the long block.

## Style and palette (shared, `plots/motivation/figstyle.py`)

ACM sigconf sizing: single column 3.33 in, double column 7.0 in (M3b and M4 only),
height at most 2.2 in per row; 8 pt body font, 7 pt ticks, one sans-serif face; vector
PDF with `pdf.fonttype 42` (no Type-3) plus a 300 dpi PNG. Error bars and bands are 95
percent bootstrap CIs (2,000 resamples, seed 0) with the resampled unit stated in each
caption, except where the source report already committed a CI (then that CI is used
and labelled). Okabe-Ito colour-blind-safe palette; every series is also given a marker
or a hatch, so no series is distinguished by colour alone.

Two colour families recur, and the same colour means the same thing within each:

- Readiness / rebuild shape (M3a, M3b, M5, M4): one-go / cold = vermillion; 2,048-piece
  = sky blue; 1,024-piece / host = green; disk = blue; gpu-warm / reload = orange.
- Device vs cloud (M1 only): device = blue, cloud = vermillion.

The device/cloud pair (M1) is a separate axis of the paper from the tier/shape family
and appears in no other figure, so its reuse of blue and vermillion carries no
cross-figure ambiguity; markers and hatches disambiguate within every figure.

---

## M1 (figM1_cloud_value): cloud value

**Data.** Panel (a): S-EMBER recall accuracy. Device arm = StudyO 4B-I x RECENT
(`results/sember/study_o/study_o_q4_trials_fa2.jsonl`, model_arm 4B-I, state_arm
RECENT, 845 questions). Cloud arm = StudyR1 K1 = 32B-I x RICH
(`results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz`, cell K1, mode batched).
The evidence-coverage split is StudyR1's own `evidence_covered` field, taken from each
question's RECENT row (outside window = covered False, inside = True). Panel (b):
StudyCTRL1b challenge mAP (`results/dashcam/ctrl1b/ctrl1b_crossfit.json`, by_budget 0.2,
all 300 clips held out).

**Selection rule.** None. Both full populations are used (845 questions; 300 clips).

**Checks.** Reproduced the StudyR1 Accuracy table exactly: cloud 42.3 (outside) / 39.2
(inside), device 20.6 / 34.4, n = 97 / 748 (report `study_r1_cloud32b_sember.md`
Accuracy table). mAP device-only 0.47760 and always-cloud 0.56753, gap +0.08993, CI
[+0.0357, +0.1497] (report `study_ctrl1b_crossfit.md` sections 3, 3.1). All ratios
this run / report = 1.000.

**Judgement.** The "two gains" are annotated as the difference of the rounded bar
heights (42.3 - 20.6 = +21.7 pp; 39.2 - 34.4 = +4.8 pp), which is what the report's
accuracy table implies and what a reader reads off the bars, rather than the
full-precision difference (21.65), so the annotation matches the report within
rounding. Panel (b) per-arm whiskers use the committed `challenge_mAP_ci`; the gap and
its CI are the committed `paired_differences` entry.

---

## M2 (figM2_interference): interference

**Data.** StudyENG1d-loadedblock. Per-trial imposed delay from
`eng1d_trials_derived.jsonl`; the plotted per-request arrivals and TTFTs from the raw
`eng1d_partC_requests_h100nvl.jsonl` (kind episodic for background, kind inject for the
action). Load P40, action mono11k.

**Selection rule (fixed).** The FIT pair whose total imposed delay is the median of the
cell's 15 FIT pairs. That is trial 16, imposed 44.87 s, exactly the cell median
(odd n, so the median pair is the cell median).

**Checks.** Pair imposed delay 44.87 s and cell median 44.87 s both equal the report's
P40 mono11k total of 44.87 s (`study_eng1d_loadedblock.md` section 7), ratio 1.000.

**Judgement.** The x-axis is arrival time within the 10 s trace, computed as
`t_submit - action_submit + inj_t`, where `inj_t` is the action's own `t_inj_rel` (its
arrival offset in the trace). The without arm is a separate run with no action, so its
points are placed at the arrival of their with-arm twin (paired by the background index
in the request id) and shown at their own measured TTFT. The shaded band is the
action's engine span (`action_span_s` = 2.60 s) from its arrival. This is a single
paired run, so no error bar is drawn; the imposed-delay annotation carries the cell
median for context. Caching: prefix caching on, both arms cold for the action and
background KV (0 cached-token mismatches).

---

## M3a (figM3a_shape): shape trade-off

**Data.** StudyENG1c-hostfull Part D per-trial rows (`eng1c_results.json` D.trials):
cold-tier arrivals on the host-full (capped) servers 27 / 38 / 60 GiB, both loads. One
point per rebuild shape (mono, piece2048, piece1024); x = job_ttft, y = imposed_s.

**Selection rule.** Cold-tier arrivals on the capped servers, which is the subset the
report's verdict D and implication 5 describe ("cold mono ~14 s; pieces ~6 s / ~3 s at
+0.7 to +1.1 s job TTFT; pieces impose about 4 to 5x less"). The 256 GiB reference
server (mostly host-warm) is excluded.

**Checks.** n = 65 / 72 / 70 cold trials. Medians: mono 2.251 s TTFT / 14.177 s
imposed; piece2048 2.963 / 5.742; piece1024 3.354 / 3.096. Every value falls inside the
report's committed cold-tier ranges (`study_eng1c_hostfull.md` section 6, verdict D):
TTFT 2.24-2.32 / 2.8-3.0 / 3.3-3.4 and imposed 14.0-16.5 / 3.8-6.2 / 2.9-3.6. Annotated
reduction factor 4.58x (report "4 to 5x") and TTFT cost +1.1 s (report "+0.7 to
+1.1 s"; implication 5 "+1 s").

**Judgement.** The report commits ranges (it aggregates the cold tier across cells
rather than a single pooled median); this figure plots the pooled cold-tier medians,
which fall inside those ranges, and the reduction factor and TTFT cost are computed
from the pooled medians. Error bars are 95 percent bootstrap CIs of the median,
resampling trials.

---

## M3b (figM3b_pieces): why pieces work

**Data.** StudyENG1e-chain step log (`eng1e_steps_A_P40.jsonl.gz`) joined to the
request rows (`eng1e_requests_h100nvl.jsonl.gz`), mode A, load P40. Each engine step is
drawn as a block; a step's engine request ids ("chatcmpl-<rid>-<8hex>") are mapped back
to the trial's request ids and the block is coloured action-only / background-only /
both. Step span = [max(dispatch ts, previous step end), t0 + elapsed_ms], the add-on's
own dispatch-based timing.

**Selection rule.** For each action the trial whose total imposed delay (latency sum)
is closest to the cell median from `eng1e_results.json cells_all`: mono cell median
39.59 s -> trial 4; chain1024 cell median 5.42 s -> trial 2. The reconstruction of the
per-trial imposed delay reproduces the committed cell medians exactly (39.59, 5.42).

**Checks.** chain1024 runs one step per piece (median steps per piece = 1.0; report
sections 5, 6: "every piece ran in one step"); mono runs two prefill steps (report).
The annotated inter-piece gap is 158 ms; the cell's committed gap median is 0.173 s
(`study_eng1e_chain.md` section 7, A chain1024 P40). The engine serves background in
the gap (report: 77-100 percent of gaps).

**Judgement.** This is a single representative trial per action, so the annotated gap
(158 ms) is the actual gap in the plotted trace, not the cell median; the cell median
(0.173 s) is cited in the figure JSON and the caption. Blocks are only the steps that
served this trial's requests, so engine-idle intervals (for example mode A mono's large
front-end window while the 22.7 MB body is preprocessed) appear as blank gaps, which is
faithful. The add-on that logged the steps failed the unloaded overhead gate and passed
at P40; this cell is loaded and both arms ran with the add-on, so the comparison is
unaffected (stated in the caption).

---

## M4 (figM4_tiers): readiness tiers (revision 1, disk removed)

**Revision 1.** The disk panel was removed: disk is not a tier in the problem setting
yet (design log D78, open question Q12). The three tiers shown are GPU-warm, host and
cold. StudyENG1f's disk data is untouched and kept for a separate later figure.

**Data.** (a) restore TTFT at the 11,184-token history, StudyENG1 Part D concurrency 1,
from `results/cost/study_eng1/eng1_partD_requests_h100nvl.jsonl` (kind query, conc 1,
role None: 30 probes per tier), cross-checked against `eng1_results.json` D.conc1
`ttft_median`. (b) delay imposed on others under load, from the one study that measured
all three tiers under a single load, StudyENG1c Part D
(`eng1c_results.json` D.trials, variant mono, host-full capped servers 27/38/60 GiB, by
tier at arrival). (c) capacity, computed from the committed D76 round-1 capacities and
the ENG1c cap table.

**Selection rule.** (a) the conc-1 probe queries (30 per tier). (b) mono-action trials
on the capped servers, grouped by the measured tier at arrival. (c) none (arithmetic).

**Checks.** (a) GPU-warm 0.10007 s, host 0.16711 s, cold 2.74287 s (n = 30 each),
reproducing spec v4 section 5.3 and `eng1_results.json` D.conc1 exactly (ratios 1.000).
(b) cold 14.18 s (n = 65) inside the report's cold-mono range 14.0-16.5 s; GPU-warm
-0.02 s (n = 11) inside the report's -0.3 to 0.2 s; host 0.04 s (n = 11), about 0
(`study_eng1c_hostfull.md` section 6). All three tiers are measured under load, so no
"not measured" bar is needed. (c) GPU pool 62,944 / 11,184 = 5.63 histories; host beyond
the GPU pool 47,648 / 11,184 = 4.26 at 27 GiB and 985,632 / 11,184 = 88.13 at 256 GiB;
cold unbounded. The token counts (62,944; 47,648 = 110,592 - 62,944; 985,632 =
1,048,576 - 62,944) are the committed ENG1c cap table (`study_eng1c_hostfull.md`
section 1); the full arithmetic is in the figure JSON.

**Judgement.** For GPU-warm under load (panel b), ENG1c Part D did measure a
GPU-resident history served under load (11 mono trials, imposed about 0 s), so that bar
carries a real value rather than a "not measured" hatch; no substitute action (such as
warm append) was used. Panel (b) is linear; the GPU-warm and host medians are about 0
(GPU-warm is -0.02 s, within noise) and are labelled "~0". Panel (c) is log-scaled with
cold drawn as an unbounded up-arrow. The GPU-pool capacity is annotated as reduced in
practice by the working space in-flight requests need (noted in the JSON). Panel (a)
uses p10 to p90 whiskers; panel (b) uses the 95 percent bootstrap CI of the median
(resampling trials).

---

## M5 (figM5_predictability): predictability

**Data.** StudyT0b-fidelity one-shot holdouts: `t0b_holdout_eng1c.json` (120 pairs) and
`t0b_holdout_eng1d.json` (60 pairs), `latency.per_trial` (measured_delay_s,
predicted_delay_s, cell). Tier per ENG1c trial from `residency.rows` (measured_state).

**Selection rule.** None; both one-shot holdout sets are plotted in full, exactly as
T0b scored them (180 points). These are the held-back pairs, the one figure for which
holdout data is the intended material.

**Checks.** Action ranking agreement 19 / 20 included pairs (StudyENG1c, report (ii)
0.9500) and 12 / 12 (StudyENG1d, report (ii) 1.0000). Chain over-prediction, per piece
size on the ENG1c holdout: predicted median / measured median = 7.780 / 5.267 = 1.48
(piece2048) and 5.290 / 2.804 = 1.89 (piece1024), reproducing the report's section 8A.1
medians exactly; annotated as "chains over-predicted 1.5-1.9x".

**Judgement.** Points are coloured by action: one go (mono11k), pieces (piece1024 +
piece2048), and reload / warm (ENG1c trials whose measured residency is host- or
gpu-warm; StudyENG1d is all cold single requests). The axes are log-log, so warm and
near-zero (and the few slightly negative) delays are clamped to a 0.02 s floor and
noted in the caption; this is a display choice and does not change any reported number.

---

## M6 (figM6_workload): real workload

**Data.** StudyE7-d2-4b Job A (`e7_requests_h100nvl.jsonl`): the per-question D2 history
size in tokens (the request's prompt_tokens under the D2 append-only representation,
sessions played from the start). Answered real questions only (grey False, infeasible
False). Cold-rebuild anchors from StudyENG1f Part 1 (`eng1f_results.json` part1 cold
recompute 11k 2.687 s, 28k 7.572 s).

**Selection rule.** None; the full answered set is plotted.

**Checks.** n = 839, min 511, max 30,701, median 10,584 tokens, reproducing the report
exactly (`study_e7_d2_4b.md` section 1: 511-30,701, p50 10,584). Cold-rebuild anchors
2.69 s (11k) and 7.57 s (28k), ratios 1.000 against StudyENG1f Part 1.

**Judgement.** "History size in tokens at the question's real time" is the D2 prompt
token count, which for the append-only D2 history is the whole context up to that
question. The cold-rebuild anchors are taken from StudyENG1f Part 1, the committed curve
that measures both 11k and 28k cold recompute on the one 32B serving stack; StudyENG1
Part B's monolithic 11k (2.755 s) agrees within 2.5 percent and is noted in the figure
JSON. Two dashed reference lines (not a continuous secondary axis) carry the two
committed anchor points, since only those two sizes have a committed cold-rebuild time.

---

## Files

- Scripts: `plots/motivation/figstyle.py`, `plots/motivation/figM{1,2,3a,3b,4,5,6}_*.py`.
- Figures: `figures/motivation/figM1_cloud_value`, `figM2_interference`, `figM3a_shape`,
  `figM3b_pieces`, `figM4_tiers`, `figM5_predictability`, `figM6_workload` (each `.pdf`,
  `.png`, `.json`).
- Captions: `figures/motivation/CAPTIONS.md`.
- This report: `reports/study_fig1_motivation.md`.
- Registry: `research/EXPERIMENTS.md` (StudyFIG1-motivation row). Index: `results/INDEX.md`.
  Status date: `research/STATUS.md`.

No result file was modified; every data source above is read-only. Nothing was
committed (the user commits with a scoped file list).
