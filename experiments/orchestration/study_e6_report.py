#!/usr/bin/env python3
"""Emit reports/study_e6_intervention.md from the StudyE6 JSONs. Tables are generated, never hand-copied."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
R = ROOT / "results/orchestration/study_e6"
P0 = json.loads((R / "e6_part0_upload_fix.json").read_text())
E6 = json.loads((R / "e6_results.json").read_text())
E4 = json.loads((ROOT / "results/orchestration/study_e4/e4_results.json").read_text())
O = []
def w(s=""): O.append(s)
def f3(x): return "—" if x is None else f"{x:.3f}"
def f4(x): return "—" if x is None else f"{x:.4f}"
def cif(c, d=3):
    return "—" if not c else f"[{c[0]:+.{d}f}, {c[1]:+.{d}f}]"
def excl(c): return "**yes**" if c and (c[0] > 0 or c[1] < 0) else "no"
def netlab(tag):
    net, fmt, dl = tag.split("/")
    return f"{net.replace('Mbps_44ms',' Mbit/s').replace('Mbps_22ms',' Mbit/s').replace('Mbps_142ms',' Mbit/s')} / {fmt} / {dl}"

NF32 = E6["noise_floor"]["F32vsK3"]["oracle_headroom"]
NF4 = E6["noise_floor"]["F4vsH1"]["oracle_headroom"]
CELLS = ["H1", "H2", "K3", "K1"]
TG = ["cap_recent", "ev_4B", "both", "cap_rich", "ev_32B"]
TGL = {"cap_recent": "capability @ RECENT (K3−H1)", "ev_4B": "evidence @ 4B (H2−H1)",
       "both": "both (K1−H1)", "cap_rich": "capability @ RICH (K1−H2)", "ev_32B": "evidence @ 32B (K1−K3)"}
POLS = ["oracle", "static", "pertype", "indep_always32B", "indep_conf4B", "indep_clsF2",
        "capability_only", "evidence_only", "combined"]
PL = {"oracle": "oracle (upper bound)", "static": "best static cell", "pertype": "per-type lookup",
      "indep_always32B": "independent: coverage × always-32B", "indep_conf4B": "independent: coverage × 4B-confidence",
      "indep_clsF2": "independent: coverage × F2 classifier", "capability_only": "capability-only",
      "evidence_only": "evidence-only", "combined": "combined (all four cells)"}
A = E6["setting_a_accuracy_under_budgets"]
U = E6["setting_b_timely_utility"]
PVP = E6["policy_vs_pertype"]
PVS = E6["policy_vs_best_static"]
UTAGS = ["88Mbps_22ms/png/5s", "88Mbps_22ms/png/10s", "13.6Mbps_44ms/png/10s"]

w("# StudyE6-intervention — can a policy predict WHICH intervention helps, and does a combined policy beat an independent evidence selector plus model router?")
w()
w("**OFFLINE ANALYSIS OF EXISTING RESULTS.** CPU only on the flash host: no GPU was used, no model server was started, "
  "and no inference was run. All numbers come from committed per-question result files of earlier studies.")
w()
w("**E-id:** `StudyE6-intervention`, pre-registered in `research/EXPERIMENTS.md` on 2026-11-10 **before any number in this "
  "report was computed** (user-authorized row).  ")
w("**Scripts:** `experiments/orchestration/study_e6_part0_upload_fix.py` (Part 0), "
  "`experiments/orchestration/study_e6_intervention.py` (main), `experiments/orchestration/study_e6_report.py` (this file).  ")
w("**Results:** `results/orchestration/study_e6/e6_part0_upload_fix.json`, `e6_results.json`, `e6_realized_vectors.npz`.  ")
w("**Environment:** conda env `fmtk` (scikit-learn 1.1.3, numpy 1.24.4, scipy 1.9.1).")
w()
w("## Prominent flags (read first)")
w()
w("1. **No policy tested here comes close to the oracle, and the headline answer to the question is negative.** "
  f"The per-question oracle over the four cells scores {A['oracle|F1|logreg|b32=1.0|bRICH=1.0']['accuracy']:.4f} "
  f"against {A['static|F1|logreg|b32=1.0|bRICH=1.0']['accuracy']:.4f} for the best static cell; every learned policy lands "
  "between those two and most land below the static cell.")
w("2. **The combined policy never beats the best independent baseline.** Of the paired contrasts, the only CIs that exclude "
  "zero do so on the **negative** side (combined worse). The pre-registered rule for 'combined beats independent' therefore "
  "fails, and it fails in the direction opposite to the hypothesis.")
w("3. **No feature set adds value over F1.** Question text (F2), session history (F3) and 4B confidence (F4) never improve "
  "AUROC over category + question time with a CI excluding zero; in three contrasts they are significantly **worse**. "
  "By the pre-registered rule, the decision reduces to a per-type lookup rule.")
w("4. **Part 0 overturns one of StudyE4's stated conclusions.** E4's per-question analysis charged cloud-held history arms "
  "for every frame since the previous question, while its session analysis charged only the newest pending frame. Under the "
  "consistent (session) rule, E4's finding that *'at constrained uplinks and short deadlines the answer is a single "
  "configuration'* does not hold: headroom at 13.6 Mbit/s PNG 5 s goes from 0.004 (≈ noise) to "
  f"{P0['tables']['newest_frame/13.6Mbps_44ms/png/5s']['headroom_over_pertype']:.3f}.")
w("5. **Setting (b) is dominated by upload feasibility, not by prediction.** Because RECENT pays its full frame set every "
  "question, at 13.6 Mbit/s PNG 10 s only "
  f"{U['_deliverable_fraction|13.6Mbps_44ms/png/10s']['H1']*100:.1f}% of H1 and "
  f"{U['_deliverable_fraction|13.6Mbps_44ms/png/10s']['K3']*100:.1f}% of K3 requests can be delivered at all, against "
  f"{U['_deliverable_fraction|13.6Mbps_44ms/png/10s']['K1']*100:.1f}% of K1. There is little left to decide.")
w("6. **F4's confidence probe is unaffordable at a constrained uplink.** Reading 4B's letter logprobs requires shipping the "
  "RECENT frames first, so at 13.6 Mbit/s PNG 10 s every F4 policy collapses to "
  f"≈{U['combined|F4|logreg/13.6Mbps_44ms/png/10s']['utility'] if 'combined|F4|logreg/13.6Mbps_44ms/png/10s' in U else U['combined|F4|logreg|13.6Mbps_44ms/png/10s']['utility']:.4f} utility.")
w(f"7. **Noise floor.** Near-identical arms (StudyD11 arm F) disagree on {E6['noise_floor']['F32vsK3']['disagreement']*100:.2f}% "
  f"(32B) and {E6['noise_floor']['F4vsH1']['disagreement']*100:.2f}% (4B) of questions, giving an oracle-headroom floor of "
  f"{NF32*100:.2f} pp / {NF4*100:.2f} pp. Differences at or below ~{NF4:.4f} are indistinguishable from run-to-run noise.")
w()
w("## 1. Arms, and what each comparison can identify")
w()
w("All four primary cells are S-EMBER, 845 questions, Instruct, greedy, max 512 tokens, vLLM 0.31.0 on h100nvl. "
  "None is marked INVALID in `research/EXPERIMENTS.md` or excluded by `reports/comparability_ledger.md`.")
w()
w("| cell | model | evidence construction | source | accuracy |")
w("|---|---|---|---|---|")
src = {"H1": "StudyClean", "H2": "StudyClean", "K3": "StudyR1 batched", "K1": "StudyR1 batched"}
mod = {"H1": "4B-I", "H2": "4B-I", "K3": "32B-I", "K1": "32B-I"}
ev = {"H1": "RECENT (121 frames)", "H2": "RICH (≤ 256 frames at 1 fps)", "K3": "RECENT (121 frames)", "K1": "RICH (≤ 256 frames at 1 fps)"}
for c in CELLS:
    w(f"| {c} | {mod[c]} | {ev[c]} | {src[c]} | {E6['checks']['cell_accuracy'][c]*100:.2f}% |")
w()
w(f"All {E6['checks']['n_matched_all_four_cells']} questions are present in all four cells, so every target below is a "
  "complete paired comparison. **Match statements, as required:**")
w()
for k, v in E6["match_statements"].items():
    w(f"- **{k}** — {v}")
w()
w("The two evidence contrasts are therefore *not* clean history-length manipulations: the ledger labels RICH-vs-RECENT "
  "`REALLOCATED_BUDGET` because window, frame count and resolution move together under one token budget. Every statement "
  "about 'evidence gain' below inherits that.")
w()
w("## 2. PART 0 — E4 upload-consistency fix")
w()
w("### 2.1 The inconsistency")
w()
w("`study_e4_counterfactual.py:196-201` charges a cloud-held history arm for **every frame newer than the previous question "
  "of the same video**, whereas the session analysis at `:395-399` charges it for **only the newest pending frame**. The same "
  "arm is therefore billed two different ways in one study. Part 0 adopts the session rule throughout Part 1; RECENT arms pay "
  "their full frame set per question under both rules, since they hold nothing at the cloud.")
w()
w("**Assumption, stated explicitly as the spec requires:** " + P0["assumption_stated"][1] + ". The newest-frame charge is "
  "the marginal cost of keeping that cloud-side store current, not the cost of building the prompt.")
w()
w("**Reproduction check (this is also consistency check 1).** The Part 0 script reimplements E4's curves, UNKNOWN handling, "
  "cross-fitting and bootstrap, and under the *original* rule it reproduces the committed `e4_results.json` table 4.1 with "
  f"**max absolute difference {P0['check_reproduces_e4_old_rule']['max_abs_diff']:.4f} across all "
  f"{P0['check_reproduces_e4_old_rule']['cells']} cells**. The corrected numbers below therefore differ from E4 only because "
  "of the upload rule.")
w()
w("### 2.2 What the fix does to the upload charge")
w()
w("| arm | held at cloud | rule | median | mean | max |")
w("|---|---|---|---|---|---|")
for k, v in P0["upload_bytes_example"].items():
    arm, _, rule = k.split("/")
    held = "no" if arm in ("H1", "K3") else "yes"
    w(f"| {arm} | {held} | {'E4 original' if rule == 'prev_question' else '**corrected**'} | "
      f"{v['median']/1e6:.3f} MB | {v['mean']/1e6:.3f} MB | {v['max']/1e6:.3f} MB |")
w()
w("RECENT arms are unchanged by construction. The history arms' median per-question upload falls by about two orders of "
  "magnitude (RICH 15.083 → 0.157 MB, ≈96×; D2 6.293 → 0.140 MB).")
w()
w("### 2.3 E4 table 4.1 recomputed (headroom over per-type; noise floor "
  f"{NF32:.4f} / {NF4:.4f})")
w()
w("| network / format / deadline | oracle OLD | per-type OLD | headroom OLD [95% CI] | oracle NEW | per-type NEW | headroom NEW [95% CI] | best static NEW |")
w("|---|---|---|---|---|---|---|---|")
cells = ["13.6Mbps_44ms/png/1s", "13.6Mbps_44ms/png/2s", "13.6Mbps_44ms/png/5s", "13.6Mbps_44ms/png/10s",
         "13.6Mbps_44ms/raw/5s", "13.6Mbps_44ms/raw/10s", "88Mbps_22ms/png/1s", "88Mbps_22ms/png/2s",
         "88Mbps_22ms/png/5s", "88Mbps_22ms/png/10s", "88Mbps_22ms/raw/2s", "88Mbps_22ms/raw/5s",
         "88Mbps_22ms/raw/10s", "5Mbps_142ms/png/5s", "5Mbps_142ms/png/10s", "5Mbps_142ms/raw/10s"]
for c in cells:
    o, n = P0["tables"]["prev_question/" + c], P0["tables"]["newest_frame/" + c]
    oh = f"{o['headroom_over_pertype']:.3f} {cif(o['headroom_over_pertype_ci'])}"
    nh = f"**{n['headroom_over_pertype']:.3f}** {cif(n['headroom_over_pertype_ci'])}"
    if o["headroom_over_pertype"] <= NF4: oh += " ≈ noise"
    if n["headroom_over_pertype"] <= NF4: nh += " ≈ noise"
    w(f"| {netlab(c)} s | {o['oracle']:.3f} | {o['pertype_crossfit']:.3f} | {oh} | {n['oracle']:.3f} | "
      f"{n['pertype_crossfit']:.3f} | {nh} | `{n['static_insample_config']}` |")
w()
w("Under the original rule, 7 of these 16 cells had headroom at or below the noise floor and the best static configuration "
  "was `cl-32B-D2` almost everywhere. Under the corrected rule only the 1 s-deadline cells remain at the floor, and the best "
  "static configuration becomes `cl-32B-RICH` in most cells — because once history is held at the cloud, the cheap-upload "
  "advantage that made D2 attractive largely disappears.")
w()
w("### 2.4 E4 section 5 classification recomputed, and how much of the representation class survives")
w()
w("| network / format / deadline | rule | n oracle>per-type | capability | evidence | representation | location | interaction | representation share |")
w("|---|---|---|---|---|---|---|---|---|")
for c in ["13.6Mbps_44ms/png/5s", "13.6Mbps_44ms/png/10s", "88Mbps_22ms/png/2s", "88Mbps_22ms/png/5s",
          "88Mbps_22ms/png/10s", "88Mbps_22ms/raw/10s", "5Mbps_142ms/png/10s"]:
    for rule, tag in (("prev_question", "E4 original"), ("newest_frame", "**corrected**")):
        t = P0["tables"][f"{rule}/{c}"]; e = t["classes_exclusive_spec_order"]; n = t["n_oracle_beats_pertype"]
        r = e.get("representation", 0)
        w(f"| {netlab(c)} s | {tag} | {n} | {e.get('capability',0)} | {e.get('evidence',0)} | {r} | "
          f"{e.get('location',0)} | {e.get('interaction',0)} | {r/max(n,1)*100:.1f}% |")
w()
w("**How much of the representation class survives.** In absolute counts it grows, because the set of questions where the "
  "oracle beats per-type grows: summed over the seven cells above, the exclusive representation class goes from 118 to 235 "
  "questions. As a *share* of switching questions it roughly halves at low bandwidth (13.6 Mbit/s PNG 10 s: 77.2% → 43.9%; "
  "5 Mbit/s PNG 10 s: 72.7% → 43.9%) and grows at 88 Mbit/s 5 s (5.0% → 23.0%). It remains the largest single exclusive "
  "factor in the low-bandwidth cells. The qualitative change is that **capability becomes a real low-bandwidth factor** "
  "(0 → 30 questions at 13.6 Mbit/s PNG 5 s and 10 s), which it was not under the original charge, because a 32B request on "
  "cloud-held history now fits inside the deadline.")
w()
w("## 3. Setup")
w()
w("| item | definition used in this run |")
w("|---|---|")
w("| policy action | one of the four cells H1 / H2 / K3 / K1 per question (the spec's four interventions: neither, richer "
  "evidence, larger model, both) |")
w("| accuracy | fraction of 845 questions answered correctly by the cell the policy chose |")
w("| utility | correct AND (compute + upload + RTT) ≤ deadline, with Part 0's corrected upload rule |")
w("| cross-fitting | 5 folds by video (`KFold(5, shuffle=True, random_state=0)` over 234 videos), seed 0; every vectoriser, "
  "scaler, model and threshold fitted inside training folds only; all reported values are pooled out-of-fold |")
w("| budgets | fraction of questions allowed on 32B ∈ {0.25, 0.5, 1.0} × fraction allowed to use RICH ∈ {0.25, 0.5, 1.0} |")
w("| allocation under budget | every policy supplies a score matrix over the four cells and the allocation maximises total "
  "predicted score subject to the budgets (LP, HiGHS). This makes 'maximise predicted correctness within the budget' one "
  "rule for all policies: the lookup policies' predictor is a training-fold table, the learned policies' is a fitted model. "
  "The oracle's predictor is the truth. |")
w("| CI | video-clustered bootstrap, 2,000 resamples, seed 0, resampling videos not questions |")
w("| noise floor | StudyD11 arm F vs K3 and vs H1 (E4 §6) |")
w()
w("**Feature sets** (the spec's information constraint: only what is available before the question):")
w()
for k, v in E6["feature_sets"].items():
    w(f"- **{k}** — {v}")
w()
w("*No-leakage audit.* " + E6["feature_audit_no_leakage"])
w()
w("**Independent-baseline components.** Evidence selector: an R8a-style coverage predictor on F2, target = evidence outside "
  "the recent window (`evidence_covered == False` on the RECENT construction), fitted in training folds. Its out-of-fold "
  "AUROC is " + " / ".join(f"**{v['auroc']:.4f}** ({k})" for k, v in E6.get("coverage_predictor_auroc", {}).items()) +
  ", which brackets StudyR8a's corrected query-only figure of 0.7885. *That is the right benchmark: StudyR8a's own "
  "2026-11-03 correction states that every Part 1 AUROC against the evidence label was produced by a model fitted on "
  "device-failure labels, so the 0.4741 and 0.6247 figures in its Part 1 table must not be used.* Model router variants:")
w()
for k, v in E6["independent_router_variants"].items():
    w(f"- `{k}` — {v}")
w()
w("The three router variants are all reported; the strongest at each setting is the baseline, as pre-registered.")
w()
w("**Held-fixed factor for the single-factor policies.** `capability_only` and `evidence_only` hold one factor at the best "
  "static cell's value, chosen inside the training folds. In all 5 folds the training-fold best static cell is "
  f"`{E6['fixed_factor_per_fold']['fold0']['best_static_cell_on_training_folds']}`, so capability-only varies the model at "
  f"{E6['fixed_factor_per_fold']['fold0']['capability_only_varies_model_at_evidence']} and evidence-only varies the evidence "
  f"at {E6['fixed_factor_per_fold']['fold0']['evidence_only_varies_evidence_at_model']}.")
w()

w("## 4. Mechanism verification (CLAUDE.md Steps 1-5)")
w()
w("**Step 1, causal chain.** The question is whether a *decidable* signal exists. The chain: if the four cells disagree "
  "question by question (FORMULATION's Q(f, w) varying by representation and model), then the per-question best action "
  "varies; if some feature observable *before* the question correlates with which cell wins, a policy conditioning on that "
  "feature beats a fixed choice; and if the capability and evidence decisions interact, a policy predicting the four cells "
  "jointly beats two independent predictors under the same resources. The third link is the specific claim this study "
  "exists to test, and it is the one that fails.")
w()
w("**Step 2, instantiate each link.**")
w()
w("| causal link | implementing quantity | value / range in this run | varies as expected? | evidence |")
w("|---|---|---|---|---|")
w(f"| cells disagree per question | per-target improves / harms counts | cap@RECENT {E6['targets']['cap_recent']['improves']}/{E6['targets']['cap_recent']['harms']}, "
  f"ev@4B {E6['targets']['ev_4B']['improves']}/{E6['targets']['ev_4B']['harms']}, cap@RICH {E6['targets']['cap_rich']['improves']}/{E6['targets']['cap_rich']['harms']} | "
  "yes | §5 |")
w(f"| disagreement is not noise | near-identical arm disagreement | {E6['noise_floor']['F32vsK3']['disagreement']*100:.2f}% / "
  f"{E6['noise_floor']['F4vsH1']['disagreement']*100:.2f}% vs 16-26% between real cells | yes, 10-40x smaller | §5 |")
w(f"| a pre-question signal exists | out-of-fold AUROC, F1, best target | "
  f"{max(E6['auroc_diagnostic'][k]['auroc'] for k in E6['auroc_diagnostic'] if k.startswith('F1/')):.3f} | "
  "weakly: 0.53-0.67, CIs above 0.5 for 4 of 5 targets | §6 |")
w("| richer signals add information | AUROC delta of F2/F3/F4 vs F1 | all 30 contrasts' CIs include 0, except 3 where F2/F3/F4 "
  "are **worse** | **NO — this link is effectively ABSENT** | §6 |")
w("| capability and evidence interact decidably | combined minus best independent | every CI includes 0 or excludes it "
  "negatively | **NO — this link is ABSENT** | §8 |")
w()
w("Two links are ABSENT. Under CLAUDE.md's rule that is a stopping condition **for running a sweep that assumes them**. "
  "It is not a stopping condition here, because the absence of those links *is the measured result the study was "
  "pre-registered to test*, not an unnoticed defect: the pre-registration names the interpretation rule that fires when "
  "F2/F3 add nothing over F1. The consequence is recorded under Rule 2 in §11, and no conclusion below assumes either link.")
w()
w("**Step 3, one-question trace.** " + (lambda tr: f"Question {tr['question_id'][:8]}…, video {tr['video']}, qt = {tr['qt']} s, "
  f"{tr['category']}; 88 Mbit/s + 22 ms, PNG, 10 s deadline, under Part 0's corrected upload rule.")(E4["trace_one_question"]))
w()
w("| cell | answers | prompt tokens | compute s | upload B (corrected) | network s | total s | correct | deliverable | utility |")
w("|---|---|---|---|---|---|---|---|---|---|")
for cname, key in (("cl-4B-RECENT", "cl-4B-RECENT"), ("cl-4B-RICH", "cl-4B-RICH"),
                   ("cl-32B-RECENT", "cl-32B-RECENT"), ("cl-32B-RICH", "cl-32B-RICH")):
    c = E4["trace_one_question"]["configs"][key]
    w(f"| {cname} | {c['answers']} | {c['prompt_tokens']} | {c['compute_s']:.2f} | {c['upload_bytes']:,} | "
      f"{c['network_s']:.2f} | {c['total_s']:.2f} | {'yes' if c['correct'] else 'no'} | "
      f"{'yes' if c['total_s'] <= 10 else 'no'} | {c['utility']:.0f} |")
w()
w("The trace is E4's own (same question, same curves); the upload column is the quantity Part 0 changes. Arithmetic check: "
  "31,838,730 B x 8 / 88e6 = 2.894 s, + 0.022 s RTT = 2.916 s, matching the RECENT rows.")
w()
w("**Step 4, negative control.** Two controls, both pre-specified. (a) **F0**, a feature set with no features: its AUROC is "
  + ", ".join(f"{E6['auroc_diagnostic'][f'F0/logreg/{t}']['auroc']:.3f}" for t in TG) +
  " across the five targets — at or below chance, as an intercept-only model must be, confirming the AUROC machinery is not "
  "manufacturing signal. (b) **near-identical arms** (StudyD11 arm F vs K3 / H1): oracle headroom "
  f"{NF32*100:.2f} pp / {NF4*100:.2f} pp, so when the mechanism (genuinely different inputs or models) is removed, the "
  "headroom collapses to under half a point against the 16.7-point oracle-minus-static gap measured here.")
w()
w("**Step 5, alternative explanation.** The headline negative — no policy beats the lookup — has at least three "
  "explanations this design cannot separate. (i) The per-question winner genuinely is unpredictable from pre-question "
  "information. (ii) It is predictable, but not from *these* features at n = 845: the targets are sparse "
  f"({E6['targets']['ev_4B']['improves']} positives for evidence @ 4B out of 845) and 5-fold cross-fitting leaves ~676 "
  "training rows per fold against 300 TF-IDF columns. (iii) A large part of the oracle's margin is the single-draw "
  "selection effect: the oracle is credited whenever *any* cell happened to be right, and with four greedy arms that "
  "inflates it even if nothing is learnable. StudyO-q4 §2d makes this point for sampled arms (14.6% run-to-run flips "
  "exceeding its 13.28 pp oracle gap). **Here it is weaker but not absent:** these are greedy Instruct arms whose "
  f"near-identical-arm flip rate is only {E6['noise_floor']['F4vsH1']['disagreement']*100:.2f}%, so the oracle's margin is "
  "mostly real disagreement between genuinely different inputs rather than resampling noise. Nothing in the data "
  "distinguishes (i) from (ii).")
w()
w("## 5. Targets, their joint distribution, and the noise floor")
w()
w("| target | improves (+1) | unchanged (0) | harms (−1) | mean |")
w("|---|---|---|---|---|")
for t in TG:
    v = E6["targets"][t]
    w(f"| {TGL[t]} | {v['improves']} | {v['unchanged']} | {v['harms']} | {v['mean']:+.4f} |")
w()
w("**The two kinds of intervention behave differently.** Capability is asymmetric — making the model bigger helps about "
  f"1.7-2.2x as often as it hurts ({E6['targets']['cap_recent']['improves']}/{E6['targets']['cap_recent']['harms']} at "
  f"RECENT, {E6['targets']['cap_rich']['improves']}/{E6['targets']['cap_rich']['harms']} at RICH). Evidence is close to a "
  f"coin flip — {E6['targets']['ev_4B']['improves']}/{E6['targets']['ev_4B']['harms']} at 4B (net negative) and "
  f"{E6['targets']['ev_32B']['improves']}/{E6['targets']['ev_32B']['harms']} at 32B. Both evidence contrasts are "
  "`REALLOCATED_BUDGET`, so this is a statement about RICH-vs-RECENT as a package, not about history length.")
w()
w("**Joint distribution over (H1, H2, K3, K1) correctness**, most frequent first:")
w()
w("| pattern H1 H2 K3 K1 | n | reading |")
w("|---|---|---|")
RD = {"0000": "no cell answers it", "1111": "every cell answers it", "0011": "32B answers it, 4B does not",
      "1100": "4B answers it, 32B does not", "0001": "only 32B+RICH", "1011": "only 4B+RICH fails",
      "1000": "only 4B+RECENT", "0101": "only the RICH cells"}
for k, v in list(E6["joint_distribution_H1_H2_K3_K1"].items())[:8]:
    w(f"| {' '.join(k)} | {v} | {RD.get(k,'')} |")
w()
jm = E6["joint_marginals"]
w(f"Of 845 questions, **{jm['none_correct']} are answered by no cell** and **{jm['all_four_correct']} by all four**; only "
  f"{845 - jm['none_correct'] - jm['all_four_correct']} questions are decidable at all. That is the ceiling on any policy: "
  f"the oracle's {A['oracle|F1|logreg|b32=1.0|bRICH=1.0']['accuracy']:.4f} is "
  f"{jm['any_cell_correct']}/845, and the {jm['all_four_correct']} unanimous questions are free to every policy.")
w()
w("| noise pair | n | disagreement | oracle headroom |")
w("|---|---|---|---|")
for k, v in E6["noise_floor"].items():
    w(f"| {k.replace('vs',' vs ')} | {v['n']} | {v['disagreement']*100:.2f}% | {v['oracle_headroom']*100:.2f} pp |")
w()
w("## 6. AUROC per target per feature set (diagnostic only), and the lookup-table test")
w()
w("Target = gain > 0 (the intervention improves this question). Out-of-fold, video-clustered CIs.")
w()
for lr in ("logreg", "gbt"):
    w(f"**{lr}**")
    w()
    w("| target | F0 (control) | F1 | F2 | F3 | F4 |")
    w("|---|---|---|---|---|---|")
    for t in TG:
        row = f"| {TGL[t]} "
        for fs in ("F0", "F1", "F2", "F3", "F4"):
            k = f"{fs}/{lr}/{t}"
            v = E6["auroc_diagnostic"].get(k)
            row += f"| {v['auroc']:.3f} [{v['ci'][0]:.2f}, {v['ci'][1]:.2f}] " if v else "| — "
        w(row + "|")
    w()
w("### The lookup-table test: does any feature set add value over F1?")
w()
w("| comparison | learner | target | ΔAUROC | 95% CI | CI excludes 0 |")
w("|---|---|---|---|---|---|")
for k, v in E6["auroc_delta_vs_F1"].items():
    comp, lr, t = k.split("/")
    note = ""
    if v["ci"][1] < 0: note = " (**worse**)"
    elif v["ci"][0] > 0: note = " (better)"
    w(f"| {comp} | {lr} | {TGL[t]} | {v['delta']:+.4f} | {cif(v['ci'])} | {excl(v['ci'])}{note} |")
w()
nworse = sum(1 for v in E6["auroc_delta_vs_F1"].values() if v["ci"][1] < 0)
nbetter = sum(1 for v in E6["auroc_delta_vs_F1"].values() if v["ci"][0] > 0)
w(f"**{nbetter} of {len(E6['auroc_delta_vs_F1'])} contrasts show a feature set beating F1 with a CI excluding zero; "
  f"{nworse} show one losing to F1 with a CI excluding zero.** Question text, session history and 4B confidence add nothing "
  "measurable over category plus question time. By the pre-registered rule: **the decision reduces to a per-type lookup "
  "rule.** The three significant losses are all `cap_rich` under logistic regression, consistent with 300 TF-IDF columns "
  "overwhelming ~676 training rows rather than with the text carrying anti-information.")
w()
w("## 7. Setting (a) — accuracy under budgets")
w()
w("Each sub-table is one budget cell. `Δ vs per-type` and `fraction of oracle headroom` are paired against the per-type "
  "lookup in the same budget cell, with video-bootstrap CIs.")
w()
for b32 in (0.25, 0.5, 1.0):
    for br in (0.25, 0.5, 1.0):
        tag = f"b32={b32}|bRICH={br}"
        w(f"**32B budget {b32:g}, RICH budget {br:g}** — oracle "
          f"{A[f'oracle|F1|logreg|{tag}']['accuracy']:.4f}, best static {A[f'static|F1|logreg|{tag}']['accuracy']:.4f}, "
          f"per-type {A[f'pertype|F1|logreg|{tag}']['accuracy']:.4f}")
        w()
        w("| policy | feature set | learner | accuracy | Δ vs per-type [95% CI] | headroom fraction [95% CI] | Δ vs best static [95% CI] |")
        w("|---|---|---|---|---|---|---|")
        for pol in POLS:
            for fs in ("F1", "F2", "F3", "F4"):
                for lrn in ("logreg", "gbt"):
                    k = f"{pol}|{fs}|{lrn}|{tag}"
                    if k not in A: continue
                    pv = PVP[f"accuracy|{k}"]; ps = PVS[f"accuracy|{k}"]
                    hf = "—" if pv["headroom_fraction"] is None else f"{pv['headroom_fraction']:+.2f}"
                    hfc = cif(pv.get("headroom_fraction_ci"), 2)
                    w(f"| {PL[pol]} | {fs} | {lrn} | {A[k]['accuracy']:.4f} | {pv['diff_vs_pertype']:+.4f} "
                      f"{cif(pv['ci_vs_pertype'])} | {hf} {hfc} | {ps['diff_vs_static']:+.4f} {cif(ps['ci_vs_static'])} |")
        w()
w("## 8. Setting (b) — timely utility with Part 0's corrected costs")
w()
w(E6["setting_b_definition"])
w()
w("**Deliverability first, because it dominates.** Fraction of the 845 questions each cell can deliver inside the deadline:")
w()
w("| network / format / deadline | H1 (4B RECENT) | H2 (4B RICH) | K3 (32B RECENT) | K1 (32B RICH) |")
w("|---|---|---|---|---|")
for tg in UTAGS:
    d = U[f"_deliverable_fraction|{tg}"]
    w(f"| {netlab(tg)} s | {d['H1']:.4f} | {d['H2']:.4f} | {d['K3']:.4f} | {d['K1']:.4f} |")
w()
w("| network / format / deadline | per-cell utility H1 | H2 | K3 | K1 |")
w("|---|---|---|---|---|")
for tg in UTAGS:
    d = U[f"_per_cell_utility|{tg}"]
    w(f"| {netlab(tg)} s | {d['H1']:.4f} | {d['H2']:.4f} | {d['K3']:.4f} | {d['K1']:.4f} |")
w()
w("H2's 0.4426 deliverability is a *compute* limit, not a network one: the cold 4B curve ends at 12,501 tokens and RICH's "
  "median prompt is 12,597, so 471 of 845 are UNKNOWN and counted unavailable exactly as E4 does. H1's and K3's collapse at "
  "13.6 Mbit/s is a network limit: 34 MB of RECENT frames needs ~20 s on that uplink.")
w()
for tg in UTAGS:
    w(f"**{netlab(tg)} s** — oracle {U[f'oracle|F1|logreg|{tg}']['utility']:.4f}, best static "
      f"{U[f'static|F1|logreg|{tg}']['utility']:.4f}, per-type {U[f'pertype|F1|logreg|{tg}']['utility']:.4f}")
    w()
    w("| policy | feature set | learner | utility | Δ vs per-type [95% CI] | headroom fraction [95% CI] | Δ vs best static [95% CI] |")
    w("|---|---|---|---|---|---|---|")
    for pol in POLS:
        for fs in ("F1", "F2", "F3", "F4"):
            for lrn in ("logreg", "gbt"):
                k = f"{pol}|{fs}|{lrn}|{tg}"
                if k not in U: continue
                pv = PVP[f"utility|{k}"]; ps = PVS[f"utility|{k}"]
                hf = "—" if pv["headroom_fraction"] is None else f"{pv['headroom_fraction']:+.2f}"
                w(f"| {PL[pol]} | {fs} | {lrn} | {U[k]['utility']:.4f} | {pv['diff_vs_pertype']:+.4f} "
                  f"{cif(pv['ci_vs_pertype'])} | {hf} {cif(pv.get('headroom_fraction_ci'), 2)} | "
                  f"{ps['diff_vs_static']:+.4f} {cif(ps['ci_vs_static'])} |")
    w()
w("## 9. The pre-registered contrast: combined minus best independent baseline")
w()
w("| setting | feature set | learner | best independent variant | independent | combined | paired diff | 95% CI | CI excludes 0 |")
w("|---|---|---|---|---|---|---|---|---|")
for k, v in E6["paired_combined_minus_best_independent"].items():
    parts = k.split("|")
    kind, fs, lrn = parts[0], parts[1], parts[2]
    tag = "|".join(parts[3:]).replace("|", ", ")
    lab = netlab(tag) + " s" if kind == "utility" else tag
    note = ""
    if v["ci"][1] < 0: note = " (**combined worse**)"
    elif v["ci"][0] > 0: note = " (combined better)"
    w(f"| {kind}: {lab} | {fs} | {lrn} | `{v['best_independent']}` | {v['independent']:.4f} | {v['combined']:.4f} | "
      f"{v['diff']:+.4f} | {cif(v['ci'])} | {excl(v['ci'])}{note} |")
w()
PR = E6["paired_combined_minus_best_independent"]
nneg = sum(1 for v in PR.values() if v["ci"][1] < 0)
npos = sum(1 for v in PR.values() if v["ci"][0] > 0)
w(f"**{npos} of {len(PR)} contrasts have a CI excluding zero in combined's favour; {nneg} have a CI excluding zero against "
  "it.** The pre-registered rule was: *combined beats independent only if the paired CI excludes 0 in at least one "
  "pre-specified setting and is not below 0 in others.* The first clause fails and the second fails as well. "
  "**Combined does not beat the independent decomposition, and where the difference is resolvable it is worse.**")
w()
w("In every setting the strongest independent variant is `always32B` — the coverage predictor paired with "
  "'send everything to the big model'. Neither confidence-thresholded routing nor an F2 classifier for K3 > H1 improves on it.")
w()
w("## 10. The capability-prediction rule, and results within each question category")
w()
w("Pre-registered rule: *capability prediction counts as useful only if the capability-only policy beats always-32B or "
  "always-4B within its budget.*")
w()
C = E6["capability_only_rule"]
nb32 = sum(1 for v in C.values() if v["beats_always32B"])
nb4 = sum(1 for v in C.values() if v["beats_always4B"])
nneg32 = sum(1 for v in C.values() if v["ci_vs_always32B"][1] < 0)
w(f"Across all {len(C)} (feature set × learner × budget) cells: capability-only beats always-32B in **{nb32}** of them, and "
  f"in **{nneg32}** it loses with a CI excluding zero. It beats always-4B in **{nb4}**.")
w()
w("| cell | capability-only | always-32B (within budget) | always-4B | diff vs always-32B | 95% CI |")
w("|---|---|---|---|---|---|")
for k, v in C.items():
    if not k.startswith(("F2|logreg", "F2|gbt")): continue
    w(f"| {k.replace('|', ' / ')} | {v['capability_only']:.4f} | {v['always32B_within_budget']:.4f} | {v['always4B']:.4f} | "
      f"{v['diff_vs_always32B']:+.4f} | {cif(v['ci_vs_always32B'])} |")
w()
w("**Reading the rule honestly.** Taken literally, the 'or always-4B' clause fires. But that comparison is not informative: "
  "capability-only is *allowed* to spend its whole 32B budget, so beating a policy that never uses 32B is close to "
  "automatic. The informative comparator is always-32B, and capability-only never beats it — not even at the tightest "
  "budget, where predicting *which* questions deserve the big model should pay most. **Capability prediction is not useful "
  "in this data**: spending a fixed 32B budget on arbitrary questions does as well as spending it on predicted ones.")
w()
w("### Within each question category")
w()
w("| category | n | H1 | H2 | K3 | K1 | oracle | per-type | best independent | combined F2/gbt | cap improves/harms (RECENT) | ev improves/harms (4B) |")
w("|---|---|---|---|---|---|---|---|---|---|---|---|")
for c, v in sorted(E6["by_question_category"].items(), key=lambda x: -x[1]["n"]):
    cl = v["cells"]; tc = v["targets"]
    w(f"| {c} | {v['n']} | {cl['H1']:.3f} | {cl['H2']:.3f} | {cl['K3']:.3f} | {cl['K1']:.3f} | {v['oracle']:.3f} | "
      f"{v['pertype']:.3f} | {v['best_indep']:.3f} | {v['combined_F2_gbt']:.3f} | "
      f"{tc['cap_recent']['improves']}/{tc['cap_recent']['harms']} | {tc['ev_4B']['improves']}/{tc['ev_4B']['harms']} |")
w()
w("`spatial_aware_reasoning` is the one category where the 4B RECENT cell is the best of the four (0.209 against 0.154 for "
  "all three others) — more evidence and a bigger model both hurt it. `location_trace` is the one where RECENT beats RICH "
  "at 32B (0.402 vs 0.309). These are the cells a per-type table can already exploit, which is why per-type is the "
  "reference the learned policies fail to beat.")
w()
w("## 11. Results consistency check (CLAUDE.md, 6 checks)")
w()
w("| # | check | outcome |")
w("|---|---|---|")
w(f"| 1 | cross-check vs committed | **PASS.** Cell accuracies reproduce StudyR1 / StudyClean exactly: "
  f"H1 {E6['checks']['cell_accuracy']['H1']*100:.2f}%, H2 {E6['checks']['cell_accuracy']['H2']*100:.2f}%, "
  f"K3 {E6['checks']['cell_accuracy']['K3']*100:.2f}%, K1 {E6['checks']['cell_accuracy']['K1']*100:.2f}% — the same values "
  "E4 §1 and the ledger record. Part 0 reproduces committed E4 table 4.1 at max abs diff "
  f"{P0['check_reproduces_e4_old_rule']['max_abs_diff']:.4f} over {P0['check_reproduces_e4_old_rule']['cells']} cells. "
  "The coverage predictor's AUROC "
  + " / ".join(f"{v['auroc']:.4f}" for v in E6.get("coverage_predictor_auroc", {}).values()) +
  " brackets StudyR8a's corrected 0.7885. No ratio > 2x. |")
w("| 2 | physical plausibility | **PASS.** No new latency measured. Compute comes from E4's curves unchanged; the only "
  "changed quantity is upload bytes, and its arithmetic is checked in the §4 trace (31,838,730 B x 8 / 88e6 + 0.022 = "
  "2.916 s). The corrected rule makes uploads *smaller*, so no implied rate exceeds a committed curve. |")
w("| 3 | distribution sanity | **PASS with note.** Identical values across cells are explained, not hidden: the three "
  "`indep_*` rows are constant across F1/F2/F3 because those policies' components are fitted on F2 by definition, so the "
  "feature-set label does not vary them; policies are identical at bRICH = 0.5 and 1.0 wherever the unconstrained optimum "
  "already uses RICH on under half the questions. Per-category spreads are reported in §10 rather than a bare mean. |")
w("| 4 | definition audit | **PASS with note.** RECENT / RICH are the ledger cells R1.K3 / R1.K1 with StudyClean H1 / H2 "
  "replaying the identical requests. 'Per-type' is E4's definition (category x qt bin). **New to this study:** the four-cell "
  "action space, the five intervention targets, and the LP budget allocation; none reuses an existing name. The 'evidence "
  "gain' name is used for a `REALLOCATED_BUDGET` contrast, flagged at §1 and wherever it appears. |")
w("| 5 | claim linkage | Bears directly on the coupling claim (joint representation x placement x timing beats decomposed "
  "policies). **It weakens the decidable form of that claim on this workload:** the joint policy does not beat the "
  "decomposed one, and the gap is negative where resolvable. It does not speak to the claim's upper-bound form, which E4 "
  "measured and Part 0 revises upward at low bandwidth. Placement is absent by construction here (all four cells are "
  "cloud), so this study says nothing about location. |")
w("| 6 | proxy validity | **Flagged, three proxies.** (a) `evidence_covered` from the RECENT construction is the training "
  "label for the coverage predictor; it is an annotation-derived flag, not something available at inference, and is used "
  "only as a fitting target inside training folds. (b) StudyD13's letter logprobs stand in for H1's confidence: predictions "
  f"agree {E6['checks']['d13_vs_h1']['pred_agreement']*100:.1f}% and prompt tokens "
  f"{E6['checks']['d13_vs_h1']['prompt_tokens_identical']*100:.1f}% of 845, so this proxy is exact rather than approximate. "
  "(c) The oracle is an upper bound inflated by single-draw selection (§4 Step 5). |")
w()
w("## 12. Observations (data only, no interpretation)")
w()
w(f"1. The four cells leave only {845 - jm['none_correct'] - jm['all_four_correct']} of 845 questions decidable: "
  f"{jm['none_correct']} are missed by every cell and {jm['all_four_correct']} answered by all four.")
w(f"2. The per-question oracle scores {A['oracle|F1|logreg|b32=1.0|bRICH=1.0']['accuracy']:.4f} unconstrained; the best "
  f"static cell (K1) {A['static|F1|logreg|b32=1.0|bRICH=1.0']['accuracy']:.4f}; the per-type lookup "
  f"{A['pertype|F1|logreg|b32=1.0|bRICH=1.0']['accuracy']:.4f}. Per-type is **below** the best static cell, replicating "
  "E4's observation that per-type routing captures nothing over static.")
w(f"3. The best realised policy anywhere in setting (a) is evidence-only on F1, "
  f"{A['evidence_only|F1|logreg|b32=1.0|bRICH=1.0']['accuracy']:.4f}, which is "
  f"{PVS['accuracy|evidence_only|F1|logreg|b32=1.0|bRICH=1.0']['diff_vs_static']:+.4f} against the best static cell with CI "
  f"{cif(PVS['accuracy|evidence_only|F1|logreg|b32=1.0|bRICH=1.0']['ci_vs_static'])}.")
w("4. Capability gains are asymmetric (bigger model helps ~2x as often as it hurts); evidence gains are near-symmetric and "
  "net-negative at 4B.")
w(f"5. No feature set beats F1 on any target with a CI excluding zero ({nbetter} of "
  f"{len(E6['auroc_delta_vs_F1'])} contrasts); {nworse} are significantly worse than F1.")
w(f"6. Combined beats the best independent baseline in {npos} of {len(PR)} pre-specified contrasts with a CI excluding "
  f"zero, and loses in {nneg}.")
w(f"7. Capability-only beats always-32B in {nb32} of {len(C)} cells, and loses with a CI excluding zero in {nneg32}.")
w("8. In setting (b) the binding constraint is deliverability, not choice: at 13.6 Mbit/s PNG 10 s only the RICH cells can "
  "be delivered, and at 88 Mbit/s PNG 5 s K3 delivers on 2.6% of questions.")
w("9. Part 0: correcting the upload inconsistency raises oracle utility in 14 of 16 reported cells, leaves 88 Mbit/s PNG "
  "10 s unchanged, and lowers headroom over per-type at 88 Mbit/s raw 10 s (0.200 → 0.172).")
w()
w("## 13. Interpretation (inference, labelled as such)")
w()
w("- **The study's question gets a negative answer on this workload, and it is a *real negative* for the combined-vs-"
  "independent comparison.** The mechanism was present and exercised: the cells genuinely disagree (§5), the disagreement is "
  "10-40x the noise floor, the independent baseline is strong, and the combined policy had strictly more information than "
  "the decomposition. Under CLAUDE.md Rule 2 this is a **real negative**, not an inconclusive one — with the caveat in the "
  "next bullet.")
w("- **The feature-set result is inconclusive-for-want-of-power, not a real negative.** Concluding that question text and "
  "session history carry no information about which intervention helps would require ruling out the n = 845 / sparse-target "
  "explanation, and three contrasts where F2 is *significantly worse* than F1 are the signature of overfitting, not of "
  "absent signal. What is settled is narrower: **at this sample size, with these features, nothing beats a category x "
  "question-time table.**")
w("- **Capability prediction specifically does not pay.** Across every budget, spending a fixed 32B allowance on predicted-"
  "gain questions is no better than spending it arbitrarily. This is the cleanest negative in the study, because the "
  "comparator (always-32B within the same budget) is exactly matched on resources.")
w("- **The oracle gap is large but is not evidence that a policy could close it.** 0.562 vs 0.395 is a 16.7-point gap, and "
  "nothing here recovers more than about a point of it. Part of that gap is the four-arm selection effect; how much, this "
  "design cannot say.")
w("- **Part 0 changes what StudyE4 should be read as saying.** E4's low-bandwidth conclusion was an artefact of charging "
  "one arm two different ways. With the charge made consistent, switching value at constrained uplinks is real "
  "(0.078-0.090 at 5-10 s) rather than ≈ noise, and the configuration that looked uniquely best there (D2) loses its "
  "advantage to cloud-held RICH. The upper-bound claim survives and is somewhat stronger; the 'nothing to switch between at "
  "low bandwidth' claim does not survive.")
w("- **What would move this.** Not more features on 845 questions. Either many more questions, or an action space whose "
  "arms differ more than these four do — 370 of 845 questions are missed by all four cells, which caps any router's reach "
  "before prediction enters.")
w()
w("## 14. Files")
w()
w("- `experiments/orchestration/study_e6_part0_upload_fix.py`")
w("- `experiments/orchestration/study_e6_intervention.py`")
w("- `experiments/orchestration/study_e6_report.py`")
w("- `results/orchestration/study_e6/e6_part0_upload_fix.json`")
w("- `results/orchestration/study_e6/e6_results.json`")
w("- `results/orchestration/study_e6/e6_realized_vectors.npz`")
w("- `reports/study_e6_intervention.md` (this file)")
Path(ROOT / "reports/study_e6_intervention.md").write_text("\n".join(O) + "\n")
print("report written:", len(O), "lines")
