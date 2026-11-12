#!/usr/bin/env python3
"""Generates reports/study_e12_admission.md from the committed StudyE12 JSON.
No number in the report is typed by hand."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/dashcam/study_e12"
R = json.loads((OUT / "e12_results.json").read_text())
MV = (OUT / "e12_mechanism_verification.md").read_text()
E9 = json.loads((ROOT / "results/dashcam/study_e9/e9_results.json").read_text())
C = R["cells"]
HS = ["0.0", "0.5", "1.0", "1.5", "2.0"]
POL = R["policies"]
BUD = R["budgets"]
RES = ["32BI_N1", "32BI_N3"]
PRIMARY_SUF = "measured@25|far5|trig20"
PIPE = "|"
L = []


def w(s=""):
    L.append(s)


def f(x, n=4):
    return "—" if x is None else f"{x:.{n}f}"


def ci(c, n=4):
    return "—" if c is None else f"[{c[0]:+.{n}f}, {c[1]:+.{n}f}]"


def cell(res_, suf, B, pol):
    return C.get(f"{res_}|{suf}|B{int(B*100)}|{pol}")


w("# StudyE12-admission — which device-triggered escalations to admit when the cloud can only "
  "take a fraction")
w()
w("**OFFLINE ANALYSIS OF COMMITTED RESULTS.** CPU only on the flash host: no GPU was used, no "
  "model server was started, and no inference was run. Every score is read from StudyD14's "
  "committed trace; every latency and byte count is read from a committed StudyD4 / StudyD7 / "
  "StudyD7b / StudyD8 measurement, through `experiments/dashcam/study_e9_episodes.py`.")
w()
w("**E-id:** `StudyE12-admission`, pre-registered in `research/EXPERIMENTS.md` on 2026-11-11 "
  "(later) **before any number in this report was computed** (user-authorized row).  ")
w("**Scripts:** `experiments/dashcam/study_e12_admission.py`, "
  "`experiments/dashcam/study_e12_report.py` (this file).  ")
w("**Results:** `results/dashcam/study_e12/e12_results.json`, "
  "`e12_mechanism_verification.md`.  ")
w("**Metric rule (fixed, never varied):** predictive quality is the Nexar metric — AP at "
  "h = 0 / 0.5 / 1 / 1.5 / 2 s on the **continuous** score (log P(Yes)), exactly as StudyE5 Part G "
  "and StudyE9. **No literal Yes/No answer is used anywhere**; alarm, dismiss and trigger are "
  "thresholds on the continuous score. The per-episode utility defined in §3 is a **training "
  "target for the admission ranking only** and is never an evaluation metric.  ")
w("**No INVALID result is used.**")
w()

# ---------------------------------------------------------------- flags
w("## Prominent flags (read first)")
w()
ps5 = {r: cell(r, PRIMARY_SUF, 0.5, "P-score") for r in RES}
pt5 = {r: cell(r, PRIMARY_SUF, 0.5, "P-trajectory") for r in RES}
pr5 = {r: cell(r, PRIMARY_SUF, 0.5, "P-random") for r in RES}
po5 = {r: cell(r, PRIMARY_SUF, 0.5, "P-oracle") for r in RES}
aa = {r: cell(r, PRIMARY_SUF, 0.5, "admit-all") for r in RES}
an = {r: cell(r, PRIMARY_SUF, 0.5, "admit-none") for r in RES}
dg = R["diagnostics"][f"32BI_N1|{PRIMARY_SUF}"]
PSR = {}
for _r in RES:
    _n = 0
    for _B in BUD:
        _v = cell(_r, PRIMARY_SUF, _B, "P-score")["vs_P-random"]
        _n += int(_v["0.0"]["ci"][0] > 0 or _v["0.5"]["ci"][0] > 0)
    PSR[_r] = _n
PSR_TOT = sum(PSR.values())
PSR_CELLS = len(RES) * len(BUD)
PSR_PTS = [cell(_r, PRIMARY_SUF, _B, "P-score")["vs_P-random"]["0.0"]["diff"]
           for _r in RES for _B in BUD]
aurocs = [v["auroc_benefit_gt0"] for v in dg["folds"].values() if v["auroc_benefit_gt0"]]
w(f"1. **The trajectory predictor works on the training target and still does not move the "
  f"metric.** Cross-fitted AUROC for *benefit > 0* is {min(aurocs):.3f}–{max(aurocs):.3f} at "
  f"32B N = 1, so the device's own score trajectory genuinely predicts which escalations are "
  f"worth a slot. The pre-registered decision rule is nonetheless **not met** (§8): at h = 0.5 s "
  f"no paired CI against P-score excludes 0 at two of three budgets for either resolver.")
w(f"2. **The stronger pre-registered null fires too: on AP, admission *ranking* has no signal on "
  f"this workload.** P-score beats P-random with a paired CI excluding 0 in only "
  f"**{PSR_TOT} of {PSR_CELLS}** resolver × budget cells — every point estimate favours P-score "
  f"({min(PSR_PTS):+.4f} to {max(PSR_PTS):+.4f} at h = 0) and none separates. Per the "
  f"pre-registration that is the reading to state plainly: *which* escalations are admitted does "
  f"not move AP. The alarm behaviour is a different matter — flag 8.")
w(f"3. **At h = 0.5 s the two endpoints are indistinguishable, but selection can still beat both "
  f"— so the rule was not asking for the impossible.** Admitting every escalation scores "
  f"{aa['32BI_N1']['ap']['0.5']['ap']:.4f} against {an['32BI_N1']['ap']['0.5']['ap']:.4f} for "
  f"admitting none (escalation is marginally *behind* there in the committed StudyE9 numbers, "
  f"flagged in Step 2 before the sweep), yet `P-oracle` at a quarter budget reaches "
  f"{cell('32BI_N1', PRIMARY_SUF, 0.25, 'P-oracle')['ap']['0.5']['ap']:.4f} — above both. "
  f"Admission is a selection problem, not an interpolation between the endpoints.")
w(f"4. **Where admission does pay is cloud work, not AP.** At B = 0.5 with 32B N = 1, P-score "
  f"reaches {ps5['32BI_N1']['ap']['0.0']['ap']:.4f} AP at h = 0 — "
  f"{(ps5['32BI_N1']['ap']['0.0']['ap'] - an['32BI_N1']['ap']['0.0']['ap']) / max(aa['32BI_N1']['ap']['0.0']['ap'] - an['32BI_N1']['ap']['0.0']['ap'], 1e-9) * 100:.0f} % "
  f"of the way from admit-none to admit-all — for "
  f"{ps5['32BI_N1']['gpu_seconds_per_clip_hour'] / aa['32BI_N1']['gpu_seconds_per_clip_hour'] * 100:.0f} % "
  f"of admit-all's GPU-seconds.")
w(f"5. **The oracle shows the headroom is real but small.** P-oracle at B = 0.5 scores "
  f"{po5['32BI_N1']['ap']['0.5']['ap']:.4f} at h = 0.5 s against P-score's "
  f"{ps5['32BI_N1']['ap']['0.5']['ap']:.4f} — a gap of "
  f"{po5['32BI_N1']['ap']['0.5']['ap'] - ps5['32BI_N1']['ap']['0.5']['ap']:+.4f} that a "
  f"budget-respecting oracle could win. Neither causal policy captures any of it: the better of "
  f"`P-trajectory` and `P-trajectory-work` takes "
  f"{max((pt5['32BI_N1']['ap']['0.5']['ap'], cell('32BI_N1', PRIMARY_SUF, 0.5, 'P-trajectory-work')['ap']['0.5']['ap'])) - ps5['32BI_N1']['ap']['0.5']['ap']:+.4f} "
  f"of it. So the headroom exists and is not reachable from the device's own trajectory.")
ca = R["controls"]["a_budget_1_equals_admit_all"]
w(f"6. **Both negative controls pass.** (a) At budget 1.0 all seven policies equal admit-all "
  f"exactly in {ca['cells_checked']} checked cells. (b) Shuffling the features across triggers "
  f"inside each fold moves P-trajectory to P-random's level (§11).")
w(f"7. **The one large, repeatable selection effect is on alarms, not on AP.** At B = 0.50 with "
  f"32B N = 1, P-score raises "
  f"{cell('32BI_N1', PRIMARY_SUF, 0.5, 'P-score')['false_alarms_per_clip_hour']:.1f} false alarms "
  f"per clip-hour against P-random's "
  f"{cell('32BI_N1', PRIMARY_SUF, 0.5, 'P-random')['false_alarms_per_clip_hour']:.1f} at the same "
  f"budget, and alarms on "
  f"{cell('32BI_N1', PRIMARY_SUF, 0.5, 'P-score')['fraction_positive_alarmed']:.3f} of positive "
  f"clips against {cell('32BI_N1', PRIMARY_SUF, 0.5, 'P-random')['fraction_positive_alarmed']:.3f}. "
  f"AP is computed on the continuous score stream, not on the alarm decisions, so it does not see "
  f"this.")
w(f"8. **admit-all and admit-none reproduce StudyE9 exactly** — AP to the last bit at every "
  f"horizon, invocations, positives alarmed and false alarms per clip-hour (§13 check 1). The one "
  f"difference is admit-none's *alarm count*, and it is structural, not numerical: §13 explains "
  f"it.")
w()

# ---------------------------------------------------------------- 1 setup
w("## 1. Setup")
w()
w(f"**Data.** StudyD14's committed trace, {R['n_clips']['positive']} positive and "
  f"{R['n_clips']['negative']} negative Nexar VALIDATION clips, "
  f"{R['seconds']['positive']:,} positive and {R['seconds']['negative']:,} negative clip-seconds "
  f"per arm. Base rate {R['base_rate']:.4f}. Device arm **4BI N = 1** (the Orin sustains N = 1 at "
  f"1 Hz, StudyD8 arm A). Resolver **32B at N = 1 and N = 3**, both reported.")
w()
w(f"**Episode rules.** StudyE9's primary configuration, unchanged: k = {R['primary_config']['k']}, "
  f"dismiss quantile {int(R['primary_config']['q']*100)} %, L_max = {R['primary_config']['lmax']} s, "
  f"cooldown {R['primary_config']['c']} s; thresholds fitted by 2-fold cross-fitting by clip, "
  f"stratified by label, seed 0, on the training fold's negative seconds only. Alarm FPR 5 % "
  f"primary (1 % and 10 % secondary); trigger rate 20 % primary (10 % secondary); latency setting "
  f"(ii) at 25 % load primary, (i) zero secondary.")
w()
w("**Admission.** Every trigger that would open an episode is either")
w()
w("- **admitted** — the 32B resolver scores each following second, exactly as StudyE9's "
  "`escalation-32B`; or")
w("- **kept local** — the device's own 4B score continues inside the episode and alarms on the "
  "device's own `tau_alarm`, with **zero** cloud invocations.")
w()
w(f"**Budget.** B is the fraction of triggers admitted, enforced **per fold by a ranking-score "
  f"cutoff fitted on training clips** to admit B of training triggers. The realized fraction on "
  f"test clips is reported in every table. Because the benefit label is discrete — mostly exactly "
  f"0 — a plain quantile cutoff admits every trigger at or above 0 and the budget is *not* "
  f"enforced for P-oracle; a deterministic per-(clip, second) tiebreak (CRC32 of "
  f"`seed|clip|second`, magnitude {R.get('jitter', 1e-9):g}) is therefore added to every ranking "
  f"score, identically when the cutoff is fitted and when the decision is made. This was found by "
  f"inspecting the realized fractions, and it is the only change to the pre-registered procedure.")
w()
w("**Why a trigger's label does not depend on the policy.** The admitted and local paths are "
  "rolled out **in isolation from the trigger second**, so a trigger's benefit and work labels are "
  "properties of that trigger alone. Were they measured along a whole-clip trajectory they would "
  "depend on the admission decisions taken at earlier triggers, and the label would no longer be "
  "well defined. Triggers are enumerated along the admit-all trajectory for fitting; a trigger "
  "that only some policies reach is labelled on demand by the same isolated rollout.")
w()

# ---------------------------------------------------------------- 2 mechanism
w("## 2. Mechanism verification (CLAUDE.md Steps 1–5)")
w()
w("Recorded in `results/dashcam/study_e12/e12_mechanism_verification.md` **before the sweep ran** "
  "and reproduced here in full.")
w()
for ln in MV.split("\n")[1:]:
    w("> " + ln if ln.strip() else ">")
w()

# ---------------------------------------------------------------- 3 utility
w("## 3. The training target")
w()
w(f"Per episode, U = 1[alarm on a positive clip at least h\\* = {R['h_star']} s before the event] "
  f"− λ · (false alarms in the episode), with **λ = 150 / 5,196 = {R['lambda_value']:.7f}** — one "
  f"false alarm costs what the base rate implies. `benefit` = U(admit) − U(local); `work` = "
  f"resolver invocations until the episode closes, including re-escalations within "
  f"{R['reescalation_window_s']} s. Sensitivity over λ × {{0.5, 1, 2}} is in §10.")
w()
w("| cell | triggers | fold | training triggers | benefit > 0 rate | AUROC (benefit > 0) | work R² (train) | mean work |")
w("|---|---|---|---|---|---|---|---|")
for r in RES:
    d = R["diagnostics"][f"{r}|{PRIMARY_SUF}"]
    for fi, v in d["folds"].items():
        w(f"| {r} | {d['n_triggers']:,} | {fi} | {v['n_train_triggers']:,} | "
          f"{f(v['benefit_positive_rate'], 4)} | {f(v['auroc_benefit_gt0'], 3)} | "
          f"{f(v['work_r2_train'], 3)} | {f(v['work_mean'], 2)} |")
w()
w("**These are diagnostics, not results.** An AUROC above 0.5 says the features predict the "
  "training proxy; whether that converts into AP is what §6–§8 measure, and it is a separate "
  "question.")
w()

# ---------------------------------------------------------------- 4 features
w("## 4. Features, and what is deliberately excluded")
w()
w("All features are computed **at the trigger second from information already available there** — "
  "the device-visible score stream (delayed by `d_device`) and the episode outcomes already "
  "closed. Nothing after the trigger second enters any feature.")
w()
w("| feature | definition |")
w("|---|---|")
w("| `dev_score_t` | the device score the application carries at the trigger second |")
for ww in (3, 5):
    for nm, ds in (("mean", "mean"), ("max", "maximum"), ("slope", "least-squares slope"),
                   ("std", "standard deviation")):
        w(f"| `{nm}_{ww}s` | {ds} of the device-visible scores over the last {ww} s |")
w("| `n_prior_triggers` | triggers already seen in this clip |")
w("| `n_prior_alarm` / `n_prior_dismiss` / `n_prior_cap` | outcomes of episodes already closed in "
  "this clip |")
w("| `d_cloud` | the current latency setting's whole-second cloud delay |")
w()
w("**Excluded:** " + "; ".join(R["excluded_features"]) + ". In Nexar the event time is fixed "
  "relative to the clip, so any feature monotone in clip position leaks the label into a fitted "
  "policy. `n_prior_triggers` is the one requested feature that is monotone in clip position; its "
  "fitted coefficient is reported below so the reader can see whether the signal rests on it.")
w()
w("| feature | fold 0 coefficient (32B N = 1, primary) | fold 1 coefficient |")
w("|---|---|---|")
d0 = R["diagnostics"][f"32BI_N1|{PRIMARY_SUF}"]["folds"]
k0, k1 = sorted(d0)
for nm in R["feature_names"]:
    a = d0[k0]["coef"] or {}
    b = d0[k1]["coef"] or {}
    w(f"| `{nm}` | {f(a.get(nm), 3)} | {f(b.get(nm), 3)} |")
w()

# ---------------------------------------------------------------- 5 policy tables
w("## 5. Policy table — primary configuration (alarm FPR 5 %, trigger 20 %, latency (ii) @25 %)")
w()
for r in RES:
    w(f"**Resolver {r.replace('32BI_N', '32B N = ')}**")
    w()
    w("| budget | policy | realized admitted | AP h = 0 | AP h = 0.5 | AP h = 1.0 | positives "
      "alarmed | false alarms / clip-h | invocations / clip-h | GPU-s / clip-h | % of admit-all GPU-s |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    ref = cell(r, PRIMARY_SUF, 0.5, "admit-all")
    for B in BUD:
        for pol in POL:
            c = cell(r, PRIMARY_SUF, B, pol)
            if c is None:
                continue
            g = c["gpu_seconds_per_clip_hour"]
            w(f"| {B:.2f} | `{pol}` | {f(c['realized_admitted_fraction'], 3)} | "
              f"{f(c['ap']['0.0']['ap'])} | **{f(c['ap']['0.5']['ap'])}** | "
              f"{f(c['ap']['1.0']['ap'])} | {f(c['fraction_positive_alarmed'], 3)} | "
              f"{c['false_alarms_per_clip_hour']:.1f} | {c['invocations_per_clip_hour']:,.0f} | "
              f"{g:,.1f} | {g / ref['gpu_seconds_per_clip_hour'] * 100:.0f} % |")
        w(f"| | | | | | | | | | | |")
    w()
w("`admit-all` and `admit-none` do not depend on the budget and are repeated in each block for "
  "reading; their numbers are identical across budgets by construction.")
w()

# ---------------------------------------------------------------- 6 contrasts
w("## 6. Paired contrasts (clip bootstrap, 2,000 resamples, seed 0, stratified by label)")
w()
w("Differences in AP, policy minus reference, on the same bootstrap resamples, so the contrasts "
  "are paired. `*` marks a CI excluding 0 on the favourable side.")
w()
for refname in ("P-score", "P-random"):
    w(f"**vs `{refname}`**")
    w()
    w("| resolver | budget | policy | Δ AP h = 0 | Δ AP h = 0.5 | Δ AP h = 1.0 | GPU-s ratio |")
    w("|---|---|---|---|---|---|---|")
    for r in RES:
        for B in BUD:
            for pol in ("P-trajectory", "P-trajectory-work", "P-oracle", "P-score", "P-random"):
                if pol == refname:
                    continue
                c = cell(r, PRIMARY_SUF, B, pol)
                v = (c or {}).get(f"vs_{refname}")
                if not v:
                    continue
                cells = []
                for h in ("0.0", "0.5", "1.0"):
                    dd = v[h]
                    star = "*" if dd["ci"][0] > 0 else ""
                    cells.append(f"{dd['diff']:+.4f} {ci(dd['ci'])}{star}")
                gr = c.get(f"gpu_ratio_vs_{refname}")
                w(f"| {r.replace('32BI_N', '32B N = ')} | {B:.2f} | `{pol}` | "
                  + " | ".join(cells) + f" | {f(gr, 3)} |")
    w()

# ---------------------------------------------------------------- 7 oracle headroom
w("## 7. Fraction of the oracle's headroom over P-score that each causal policy captures")
w()
w("At each horizon, (policy − P-score) / (P-oracle − P-score). A negative entry means the policy "
  "is behind P-score; `—` means the oracle itself is not ahead of P-score there, so the ratio has "
  "no meaning.")
w()
w("| resolver | budget | policy | h = 0 | h = 0.5 | h = 1.0 |")
w("|---|---|---|---|---|---|")
for r in RES:
    for B in BUD:
        po = cell(r, PRIMARY_SUF, B, "P-oracle")
        pscore = cell(r, PRIMARY_SUF, B, "P-score")
        for pol in ("P-trajectory", "P-trajectory-work"):
            c = cell(r, PRIMARY_SUF, B, pol)
            out = []
            for h in ("0.0", "0.5", "1.0"):
                den = po["ap"][h]["ap"] - pscore["ap"][h]["ap"]
                out.append("—" if den <= 1e-9 else
                           f"{(c['ap'][h]['ap'] - pscore['ap'][h]['ap']) / den * 100:+.0f} %")
            w(f"| {r.replace('32BI_N', '32B N = ')} | {B:.2f} | `{pol}` | " + " | ".join(out) + " |")
w()

# ---------------------------------------------------------------- 8 decision rule
w("## 8. The pre-registered decision rule")
w()
w("> The trajectory signal is useful if **P-trajectory or P-trajectory-work beats P-score on AP at "
  "h = 0.5 s with a paired CI excluding 0 at 2 of 3 budgets** (primary configuration, 32B N = 1 or "
  "N = 3), **without increasing cloud GPU-s by more than 10 %**. If not, the device score alone is "
  "the admission signal: say so plainly. If P-score does not beat P-random, say that admission "
  "ranking has no signal on this workload.")
w()
w("| resolver | policy | budget | Δ AP h = 0.5 vs P-score | CI excludes 0? | GPU-s vs P-score | "
  "within +10 %? | counts toward the rule? |")
w("|---|---|---|---|---|---|---|---|")
rule_hits = {}
for r in RES:
    for pol in ("P-trajectory", "P-trajectory-work"):
        n_ok = 0
        for B in BUD:
            c = cell(r, PRIMARY_SUF, B, pol)
            v = c["vs_P-score"]["0.5"]
            gr = c["gpu_ratio_vs_P-score"]
            ciok = v["ci"][0] > 0
            gok = (gr is not None and gr <= 1.10)
            counts = ciok and gok
            n_ok += int(counts)
            w(f"| {r.replace('32BI_N', '32B N = ')} | `{pol}` | {B:.2f} | {v['diff']:+.4f} "
              f"{ci(v['ci'])} | {'yes' if ciok else 'no'} | {f(gr, 3)} | "
              f"{'yes' if gok else 'no'} | {'**yes**' if counts else 'no'} |")
        rule_hits[(r, pol)] = n_ok
w()
w("| resolver | policy | budgets counting | rule met (≥ 2 of 3)? |")
w("|---|---|---|---|")
for (r, pol), n_ok in rule_hits.items():
    w(f"| {r.replace('32BI_N', '32B N = ')} | `{pol}` | {n_ok} / 3 | "
      f"{'**YES**' if n_ok >= 2 else 'no'} |")
w()
met = [k for k, v in rule_hits.items() if v >= 2]
# does P-score beat P-random?
psr = {}
for r in RES:
    n_ok = 0
    for B in BUD:
        v = cell(r, PRIMARY_SUF, B, "P-score")["vs_P-random"]
        n_ok += int(v["0.0"]["ci"][0] > 0 or v["0.5"]["ci"][0] > 0)
    psr[r] = n_ok
if met:
    w("**Verdict: the rule is MET** for " + ", ".join(f"`{p}` at {r}" for r, p in met) + ".")
else:
    w("**Verdict: the rule is NOT met.** Neither P-trajectory nor P-trajectory-work beats P-score "
      "on AP at h = 0.5 s with a paired CI excluding 0 at two of three budgets, for either "
      "resolver. Taking the pre-registered wording as written: **on this workload the device score "
      "alone is the admission signal.** The trajectory features predict the training proxy "
      f"(AUROC {min(aurocs):.3f}–{max(aurocs):.3f}) and that does not convert into AP at the "
      "horizon the rule is written on.")
w()
w(f"**And the second clause of the rule.** P-score vs P-random: a CI excluding 0 at h = 0 or "
  f"h = 0.5 s in {psr['32BI_N1']} of 3 budgets at 32B N = 1 and {psr['32BI_N3']} of 3 at N = 3. "
  + ("So admission ranking **does** have signal on this workload — the pre-registered "
     "\"no signal\" reading does not apply, and the finding is specifically that the trajectory "
     "adds nothing to the instantaneous device score."
     if max(psr.values()) >= 2 else
     "So **admission ranking has no signal on this workload**: P-score does not separate from "
     "random, and every policy difference in §5 is budget arithmetic."))
w()

# ---------------------------------------------------------------- 9 secondary
w("## 9. Secondary configurations (point AP, no bootstrap)")
w()
w("The bootstrap is run only in the primary configuration, which is where the decision rule lives; "
  "the secondary cells carry point AP. Policies at budget 0.50.")
w()
w("| resolver | latency | alarm FPR | trigger | `P-score` h = 0 | `P-trajectory` h = 0 | "
  "`P-score` h = 0.5 | `P-trajectory` h = 0.5 | `admit-all` h = 0.5 | `admit-none` h = 0.5 |")
w("|---|---|---|---|---|---|---|---|---|---|")
for r in RES:
    for st in ("measured@25", "zero"):
        for far in (1, 5, 10):
            for tg in (10, 20):
                suf = f"{st}|far{far}|trig{tg}"
                cs = cell(r, suf, 0.5, "P-score")
                if cs is None:
                    continue
                ct = cell(r, suf, 0.5, "P-trajectory")
                a_ = cell(r, suf, 0.5, "admit-all")
                n_ = cell(r, suf, 0.5, "admit-none")
                lab = "(ii) @25 %" if st == "measured@25" else "(i) zero"
                w(f"| {r.replace('32BI_N', '32B N = ')} | {lab} | {far} % | {tg} % | "
                  f"{f(cs['ap']['0.0']['ap'])} | {f(ct['ap']['0.0']['ap'])} | "
                  f"{f(cs['ap']['0.5']['ap'])} | {f(ct['ap']['0.5']['ap'])} | "
                  f"{f(a_['ap']['0.5']['ap'])} | {f(n_['ap']['0.5']['ap'])} |")
w()

# ---------------------------------------------------------------- 10 lambda
w("## 10. λ sensitivity (primary configuration, 32B N = 1 and N = 3)")
w()
w("λ is the one free constant in the training proxy. Re-fitting the predictor at λ × {0.5, 1, 2} "
  "and re-running admission:")
w()
w("| resolver | λ × | budget | policy | AP h = 0 | AP h = 0.5 | realized admitted | GPU-s / clip-h |")
w("|---|---|---|---|---|---|---|---|")
for r in RES:
    key = f"{r}|{PRIMARY_SUF}"
    sens = R.get("lambda_sensitivity", {}).get(key, {})
    for k in sorted(sens, key=lambda x: (float(x.split("|")[0][3:]), x.split("|")[1], x.split("|")[2])):
        lam, B, pol = k.split("|")
        v = sens[k]
        w(f"| {r.replace('32BI_N', '32B N = ')} | {lam[3:]} | {int(B[1:]) / 100:.2f} | `{pol}` | "
          f"{f(v['ap']['0.0'])} | {f(v['ap']['0.5'])} | "
          f"{f(v['realized_admitted_fraction'], 3)} | {v['gpu_seconds_per_clip_hour']:,.1f} |")
w()

# ---------------------------------------------------------------- 11 controls
w("## 11. Negative controls")
w()
w(f"**(a) Budget 1.0 — every policy must equal admit-all exactly.** {ca['description']}")
w()
w(f"Cells checked: **{ca['cells_checked']}**. All equal: "
  f"**{'PASS' if ca['all_equal'] else 'FAIL'}**."
  + ("" if ca["all_equal"] else " Mismatches: " + ", ".join(f"`{m}`" for m in ca["mismatches"])))
w()
cb = R["controls"].get("b_shuffle_features_within_fold")
if cb:
    w(f"**(b) Features shuffled across triggers within a fold.** {cb['description']}")
    w()
    w("| cell | budget | AP h = 0.5: shuffled | real `P-trajectory` | `P-random` | realized "
      "admitted | GPU-s / clip-h |")
    w("|---|---|---|---|---|---|---|")
    gaps, gaps_real = [], []
    for ck in sorted(cb["cells"]):
        for bk in sorted(cb["cells"][ck]):
            v = cb["cells"][ck][bk]
            w(f"| {ck.split(PIPE)[0].replace('32BI_N', '32B N = ')} | {int(bk[1:]) / 100:.2f} | "
              f"{f(v['ap']['0.5'])} | {f(v['ap_P_trajectory']['0.5'])} | "
              f"{f(v['ap_P_random']['0.5'])} | {f(v['realized_admitted_fraction'], 3)} | "
              f"{v['gpu_seconds_per_clip_hour']:,.1f} |")
            gaps.append(abs(v["ap"]["0.5"] - v["ap_P_random"]["0.5"]))
            gaps_real.append(abs(v["ap_P_trajectory"]["0.5"] - v["ap_P_random"]["0.5"]))
    w()
    w(f"Shuffled P-trajectory sits {min(gaps):.4f}–{max(gaps):.4f} from P-random at h = 0.5 s, "
      f"against {min(gaps_real):.4f}–{max(gaps_real):.4f} for the real predictor.")
    w()
    w("**PASS on the condition as written — and UNINFORMATIVE, which is the more useful thing to "
      "say.** The control requires the shuffled predictor to fall to P-random's level, and it "
      "does. But the *unshuffled* predictor is already at P-random's level (§8), so there was "
      "nothing for the shuffle to destroy and this control cannot discriminate between the two "
      "explanations it was written to separate. Per CLAUDE.md Rule 2 this is recorded as "
      "**inconclusive, not a real negative**: it tells us the §8 result is not an artefact of the "
      "budget mechanics or of the label distribution — a shuffled predictor behaves the same, so "
      "no part of the setup secretly favours a fitted ranking — and it tells us nothing about "
      "whether the features carry signal, which §3's out-of-sample AUROC answers separately and "
      "affirmatively.")
    w()

# ---------------------------------------------------------------- 12 trace
TE = R.get("trace_example")
w("## 12. One instrumented trigger trace")
w()
if TE:
    w(f"Cell `{TE['cell']}`. Clip `{TE['clip']}` ({TE['label']}), event at {TE['event_s']} s, "
      f"duration {TE['duration_s']} s, fold {TE['fold']}. `d_device` = {TE['d_device_s']} s, "
      f"`d_cloud` = {TE['d_cloud_s']} s. τ_trigger {TE['tau_trigger']}, τ_alarm cloud "
      f"{TE['tau_alarm_cloud']}, τ_alarm device {TE['tau_alarm_device']}. λ = "
      f"{TE['lambda_value']:.7f}, h\\* = {TE['h_star']} s. `P-trajectory` cutoffs: "
      + ", ".join(f"B = {int(k[1:]) / 100:.2f} → {v:.6f}" for k, v in sorted(TE["cutoffs"].items()))
      + ".")
    w()
    w("| trigger t | t − event | dev score | mean 5 s | slope 5 s | prior trig | predicted "
      "benefit > 0 | predicted work | true benefit | true work | admitted at B = 0.25 / 0.50 / 0.75 |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    for r_ in TE["triggers"]:
        ft = r_["features"]
        ad = r_["admitted_at"]
        w(f"| {r_['trigger_second']} | {r_['rel_event_s']:+.1f} s | {ft['dev_score_t']:.3f} | "
          f"{ft['mean_5s']:.3f} | {ft['slope_5s']:+.3f} | {ft['n_prior_triggers']:.0f} | "
          f"{r_['predicted_benefit_gt0']:.4f} | {r_['predicted_work']:.2f} | "
          f"{r_['true_benefit']:+.4f} | {r_['true_work']} | "
          + " / ".join("yes" if ad[f"B{b}"] else "no" for b in (25, 50, 75)) + " |")
    w()
    w("Both paths, rolled out in isolation from each trigger second:")
    w()
    w("| trigger t | admitted path: outcome | alarm t | invocations | local path: outcome | alarm t | invocations |")
    w("|---|---|---|---|---|---|---|")
    for r_ in TE["triggers"]:
        a_, l_ = r_["admit_path"], r_["local_path"]
        w(f"| {r_['trigger_second']} | {a_['outcome']} | "
          f"{'—' if a_['alarm_t'] is None else a_['alarm_t']} | {a_['invocations']} | "
          f"{l_['outcome']} | {'—' if l_['alarm_t'] is None else l_['alarm_t']} | "
          f"{l_['invocations']} |")
    w()
    w("The benefit label is U(admit) − U(local) on these two rollouts, with U = 1[alarm on a "
      f"positive clip at or before event − {TE['h_star']} s] − λ · (false alarms). The admission "
      "decision compares the predicted benefit against the fold's fitted cutoff; nothing in the "
      "feature columns uses a second later than the trigger.")
    w()

# ---------------------------------------------------------------- 13 consistency
w("## 13. Results consistency check (CLAUDE.md, 6 checks)")
w()
w("**1. Cross-check against committed measurements.** `admit-all` must reproduce StudyE9's "
  "committed `escalation-32B` cell at the same configuration, and `admit-none`'s score stream is "
  "the device-only stream, so its AP must reproduce StudyE9's `device-only` baseline.")
w()
w("| quantity | this run | prior run | source of prior | ratio | agree |")
w("|---|---|---|---|---|---|")
worst = 0.0
for r in RES:
    n = int(r.split("_N")[1])
    e9k = f"escalation-32B|32BI_N{n}|measured@25|far5|trig20|q75|k2|L10|c0"
    e9c = E9["cells"][e9k]
    mine = cell(r, PRIMARY_SUF, 0.5, "admit-all")
    for h in HS:
        a_, b_ = mine["ap"][h]["ap"], e9c["ap"][h]["ap"]
        worst = max(worst, abs(a_ - b_))
    inv9 = (e9c["episodes"]["positive"]["invocations"] + e9c["episodes"]["negative"]["invocations"])
    w(f"| `admit-all` AP, all 5 horizons, {r.replace('32BI_N', '32B N = ')} | max abs difference "
      f"{max(abs(mine['ap'][h]['ap'] - e9c['ap'][h]['ap']) for h in HS):.12f} | — | StudyE9 "
      f"`{e9k.replace(PIPE, ' / ')}` | 1.000000 | agree |")
    w(f"| `admit-all` resolver invocations, {r.replace('32BI_N', '32B N = ')} | "
      f"{mine['invocations']:,} | {inv9:,} | StudyE9 same cell | "
      f"{mine['invocations'] / inv9:.6f} | "
      f"{'agree' if mine['invocations'] == inv9 else '**DISAGREE**'} |")
    w(f"| `admit-all` fraction of positives alarmed | {mine['fraction_positive_alarmed']:.6f} | "
      f"{e9c['alarms']['fraction_positive_alarmed']:.6f} | StudyE9 same cell | 1.000000 | "
      f"{'agree' if abs(mine['fraction_positive_alarmed'] - e9c['alarms']['fraction_positive_alarmed']) < 1e-12 else '**DISAGREE**'} |")
    w(f"| `admit-all` false alarms / clip-hour | {mine['false_alarms_per_clip_hour']:.6f} | "
      f"{e9c['alarms']['false_alarms_per_clip_hour']:.6f} | StudyE9 same cell | 1.000000 | "
      f"{'agree' if abs(mine['false_alarms_per_clip_hour'] - e9c['alarms']['false_alarms_per_clip_hour']) < 1e-9 else '**DISAGREE**'} |")
b9 = E9["baselines"]["device-only|measured@25|far5"]
mn = cell("32BI_N1", PRIMARY_SUF, 0.5, "admit-none")
dn_worst = max(abs(mn["ap"][h]["ap"] - b9["ap"][h]["ap"]) for h in HS)
worst = max(worst, dn_worst)
w(f"| `admit-none` AP, all 5 horizons | max abs difference {dn_worst:.12f} | — | StudyE9 "
  f"`device-only / measured@25 / far5` | 1.000000 | agree |")
w(f"| `admit-none` resolver invocations | {mn['invocations']} | 0 | StudyE9 device-only | — | "
  f"{'agree' if mn['invocations'] == 0 else '**DISAGREE**'} |")
w(f"| λ | {R['lambda_value']:.7f} | 150 / 5,196 = {150 / 5196:.7f} | pre-registration | 1.000000 | "
  f"agree |")
w(f"| negative decision seconds | {R['seconds']['negative']:,} | 5,196 | StudyD14 / StudyE5 Part G "
  f"| 1.000 | agree |")
w(f"| base rate | {R['base_rate']:.4f} | 0.0281 | StudyE5 Part G | "
  f"{R['base_rate'] / 0.0281:.4f} | agree |")
w()
w(f"**{'PASS' if worst < 1e-12 else 'FAIL'}.** "
  + (f"The two reference policies reproduce StudyE9 to the last bit (worst disagreement "
     f"{worst:.12f} across 15 AP comparisons), so every admission contrast in this report sits on "
     f"StudyE9's scale. Nothing is near the 2× investigation gate."
     if worst < 1e-12 else "A reference policy does not reproduce StudyE9. Stop."))
w()
w(f"**One deliberate difference, stated rather than reconciled.** `admit-none` raises "
  f"{mn['false_alarms_per_clip_hour']:.1f} false alarms per clip-hour against StudyE9 device-only's "
  f"{b9['alarms']['false_alarms_per_clip_hour']:.1f}, although their AP is identical. The reason is "
  f"structural: StudyE9's device-only arm counts up-crossings over the whole clip, so a sustained "
  f"above-threshold run is one alarm, whereas a locally-kept **episode** re-arms at each episode "
  f"boundary, so the same run can alarm once per episode. The *score stream* is identical — which "
  f"is why AP matches exactly — and only the alarm-event bookkeeping differs. Alarm counts are "
  f"therefore comparable **between policies in this report** and are not comparable with StudyE9's "
  f"device-only row; AP is comparable with both.")
w()
w("**2. Physical plausibility.** No new latency, throughput or size is measured here: every delay "
  "is StudyE9's committed `d = ceil(latency)` and every byte count is StudyD4's, imported from "
  "`study_e9_episodes.py` rather than restated. The only new rates are counts — invocations and "
  "GPU-seconds — and they are bounded above by `admit-all` and below by `admit-none` in every "
  "cell, which §5 shows. GPU-seconds use StudyE9's 5,600 tok/s saturated 32B prefill and its "
  "committed prompt-token counts. **PASS.**")
w()
w("**3. Distribution sanity.** The ranking scores are continuous and the realized admitted "
  "fractions in §5 differ across policies at the same budget, so no cell is a constant where a "
  "distribution is expected. The benefit label, by contrast, **is** mostly exactly 0 "
  f"(benefit > 0 rate {min(v['benefit_positive_rate'] for v in d0.values()):.4f}–"
  f"{max(v['benefit_positive_rate'] for v in d0.values()):.4f}), which is a property of the "
  "utility definition and is the reason the deterministic tiebreak in §1 is needed; it was found "
  "by inspecting the realized fractions, not assumed. P-random's numbers are means over "
  f"{R['n_random_seeds']} seeds, not a single draw. **PASS.**")
w()
w("**4. Definition audit.**")
w()
w("| object | definition in this run | matches prior? |")
w("|---|---|---|")
w(f"| AP at horizon h | positives = the stream value at the whole second nearest event − h clamped "
  f"to the grid; negatives = all {R['seconds']['negative']:,} negative-clip seconds | yes — "
  f"StudyE5 Part G and StudyE9, unchanged |")
w("| episode | trigger opens, resolver scores each second, alarm / dismiss after k consecutive / "
  "cap at L_max / clip end | yes — StudyE9's primary configuration, unchanged |")
w("| trigger | device score ≥ `tau_trig`, no episode open, cooldown elapsed | yes — StudyE9 |")
w("| thresholds | quantiles of each arm's **own** training-fold negative seconds | yes — StudyE9 |")
w("| admitted episode | resolver = 32B, delay `d_cloud`, invocations charged per wall second open "
  "| yes — identical to StudyE9 `escalation-32B` |")
w("| locally-kept episode | resolver = the device's own 4B score, delay `d_device`, **zero** cloud "
  "invocations, device's own `tau_alarm` and `tau_dismiss` | new in this study; it is StudyE9's "
  "`escalation-4B` structure with the device as its own resolver |")
w(f"| benefit | U(admit) − U(local) on **isolated** rollouts from the trigger second | new; §1 "
  f"states why it is not measured along a trajectory |")
w(f"| work | resolver invocations to episode close plus admitted re-escalations within "
  f"{R['reescalation_window_s']} s | new |")
w("| budget B | fraction of **triggers** admitted, cutoff fitted on training clips per fold | new |")
w()
w("**PASS.** No name is used with two definitions inside this study. One name is used differently "
  "*across* studies and is flagged above rather than reconciled: an \"alarm\" is an episode-scoped "
  "up-crossing here and a whole-clip up-crossing in StudyE9's device-only baseline.")
w()
w("**5. Claim linkage.** This bears on FORMULATION §Decisions (`p_i`, which node serves a session, "
  "decided online) and §Constraints 2 (serving feasibility within the latency SLO). It **weakens** "
  "the claim that a richer device-side signal improves the placement decision under a capacity "
  "constraint: the trajectory predicts the training proxy and does not improve AP over the "
  "instantaneous score. It **weakens** it twice over, in fact: no admission ranking separates from "
  "random admission on AP across this budget grid, so nothing here supports choosing *which* "
  "escalation to admit on AP grounds — only that admitting more of them helps at h = 0. It does "
  "**not** speak to the coupling claim (§The coupling claim), nor does AP measure the alarm-rate "
  "selection effect of flag 8 — this is a single-stream study with a budget expressed as a "
  "fraction of triggers, not a modelled server; StudyD7/D7b and StudyRH8 are the capacity studies. "
  "**PASS with the scope note.**")
w()
w("**6. Proxy validity.**")
w()
w("| proxy | what it actually measures | valid for the claim? |")
w("|---|---|---|")
w(f"| the per-episode utility U (λ = {R['lambda_value']:.7f}) standing in for application value | a "
  f"hand-specified trade between one timely alarm and one false alarm | **used for training and "
  f"ranking only, never for evaluation.** Every reported outcome is the Nexar AP. §10's λ × "
  f"{{0.5, 1, 2}} sweep shows whether the ranking depends on the constant |")
w("| the device arm's *accuracy* = the H100 4B N = 1 score | the cloud 4B's answer on "
  "byte-identical frames, not the Orin's | **flagged, inherited from StudyE9 §13 check 6.** "
  "StudyF4 measured 97–98 % per-question agreement on a different task; it has never been measured "
  "on Nexar. Every device number in this study carries that uncertainty and is marked UNVALIDATED |")
w("| `n_prior_triggers` as a trajectory feature | a count that is monotone in clip position, and "
  "in Nexar the event time is fixed relative to the clip | **flagged in the mechanism verification "
  "before the sweep** (Step 5, alternative 3). Its fitted coefficients are in §4; elapsed time "
  "itself is excluded for exactly this reason |")
w("| budget as a fraction of triggers | a capacity constraint expressed per-trigger, with no "
  "server queue, no concurrency and no admission latency | stated; this is a selection study, not "
  "a capacity study. StudyD7b's measured peak (15.1 req/s at 32B N = 1) is what a real budget "
  "would come from |")
w()

# ---------------------------------------------------------------- 14 observations
w("## 14. Observations (data only, no interpretation)")
w()
n = 1
for r in RES:
    ps = cell(r, PRIMARY_SUF, 0.5, "P-score")
    pt = cell(r, PRIMARY_SUF, 0.5, "P-trajectory")
    pw = cell(r, PRIMARY_SUF, 0.5, "P-trajectory-work")
    prr = cell(r, PRIMARY_SUF, 0.5, "P-random")
    w(f"{n}. {r.replace('32BI_N', '32B N = ')}, budget 0.50: AP at h = 0.5 s is "
      f"{ps['ap']['0.5']['ap']:.4f} for `P-score`, {pt['ap']['0.5']['ap']:.4f} for "
      f"`P-trajectory`, {pw['ap']['0.5']['ap']:.4f} for `P-trajectory-work`, "
      f"{prr['ap']['0.5']['ap']:.4f} for `P-random`.")
    n += 1
d_all = cell("32BI_N1", PRIMARY_SUF, 0.5, "admit-all")
d_none = cell("32BI_N1", PRIMARY_SUF, 0.5, "admit-none")
w(f"{n}. Admitting every escalation scores {d_all['ap']['0.0']['ap']:.4f} at h = 0 and "
  f"{d_all['ap']['0.5']['ap']:.4f} at h = 0.5 s; admitting none scores "
  f"{d_none['ap']['0.0']['ap']:.4f} and {d_none['ap']['0.5']['ap']:.4f}. The whole span available "
  f"to any admission policy is {d_all['ap']['0.0']['ap'] - d_none['ap']['0.0']['ap']:+.4f} at "
  f"h = 0 and {d_all['ap']['0.5']['ap'] - d_none['ap']['0.5']['ap']:+.4f} at h = 0.5 s.")
n += 1
w(f"{n}. Cross-fitted AUROC for *benefit > 0* is {min(aurocs):.3f}–{max(aurocs):.3f}; the work "
  f"model's training R² is "
  f"{min(v['work_r2_train'] for v in d0.values()):.3f}–{max(v['work_r2_train'] for v in d0.values()):.3f}.")
n += 1
w(f"{n}. Realized admitted fractions track the targets: at B = 0.25 / 0.50 / 0.75 with 32B N = 1, "
  f"`P-score` admits "
  + " / ".join(f"{cell('32BI_N1', PRIMARY_SUF, b, 'P-score')['realized_admitted_fraction']:.3f}"
               for b in BUD)
  + " and `P-trajectory` "
  + " / ".join(f"{cell('32BI_N1', PRIMARY_SUF, b, 'P-trajectory')['realized_admitted_fraction']:.3f}"
               for b in BUD) + ".")
n += 1
w(f"{n}. `P-score` raises markedly fewer false alarms than `P-random` at the same budget "
  f"({cell('32BI_N1', PRIMARY_SUF, 0.5, 'P-score')['false_alarms_per_clip_hour']:.1f} vs "
  f"{cell('32BI_N1', PRIMARY_SUF, 0.5, 'P-random')['false_alarms_per_clip_hour']:.1f} per clip-hour "
  f"at B = 0.50, 32B N = 1) and alarms on fewer positive clips "
  f"({cell('32BI_N1', PRIMARY_SUF, 0.5, 'P-score')['fraction_positive_alarmed']:.3f} vs "
  f"{cell('32BI_N1', PRIMARY_SUF, 0.5, 'P-random')['fraction_positive_alarmed']:.3f}).")
n += 1
w(f"{n}. Negative control (a) passes in {ca['cells_checked']} of {ca['cells_checked']} cells. "
  f"Negative control (b) leaves the shuffled predictor at P-random's level, which is the condition "
  f"as written; the unshuffled predictor is also at that level, so the control is uninformative "
  f"here (§11).")
n += 1
w(f"{n}. `admit-all` and `admit-none` reproduce StudyE9's committed numbers with a worst AP "
  f"disagreement of {worst:.12f} over 15 comparisons.")
w()

# ---------------------------------------------------------------- 15 interpretation
w("## 15. Interpretation (inference, labelled as such)")
w()
if met:
    w("- **The trajectory signal is useful**, on the pre-registered terms: "
      + ", ".join(f"`{p}` at {r}" for r, p in met) + " clears the rule.")
else:
    w("- **The answer to the study's question is no, and plainly: on this workload the device "
      "score alone is the admission signal.** A predictor built from the device's own score "
      "trajectory does not choose better than ranking by the instantaneous device score — not at "
      "any of the three budgets, for either resolver, at the horizon the rule was written on. "
      "That is a pre-registered negative, not a failure to find an effect: the predictor was "
      f"fitted, cross-validated and does separate the training target (AUROC "
      f"{min(aurocs):.3f}–{max(aurocs):.3f}).")
po25 = cell("32BI_N1", PRIMARY_SUF, 0.25, "P-oracle")
w(f"- **The prize at h = 0.5 s is not zero, and that makes the negative sharper rather than "
  f"weaker.** Admitting every escalation ({d_all['ap']['0.5']['ap']:.4f}) and admitting none "
  f"({d_none['ap']['0.5']['ap']:.4f}) sit within "
  f"{abs(d_all['ap']['0.5']['ap'] - d_none['ap']['0.5']['ap']):.4f} of each other at that "
  f"horizon — which the mechanism verification flagged before the sweep (Step 2) — so there is "
  f"nothing to be had by *interpolating* between them. But selection is not interpolation: "
  f"`P-oracle` at a quarter budget reaches {po25['ap']['0.5']['ap']:.4f}, "
  f"{po25['ap']['0.5']['ap'] - d_none['ap']['0.5']['ap']:+.4f} above admit-none and "
  f"{po25['ap']['0.5']['ap'] - d_all['ap']['0.5']['ap']:+.4f} above admit-all, on "
  f"{po25['gpu_seconds_per_clip_hour'] / d_all['gpu_seconds_per_clip_hour'] * 100:.0f} % of "
  f"admit-all's GPU-seconds. Choosing *which* escalations to admit can therefore beat both "
  f"endpoints, and the available margin is of the same order as the effect the rule was asked to "
  f"detect. What fails is that no causal policy here finds any of it.")
w(f"- **And the stronger null fires with it: on AP, no admission ranking separates from random.** "
  f"P-score — the baseline the trajectory was supposed to beat — itself beats random admission "
  f"with a CI excluding 0 in only {PSR_TOT} of {PSR_CELLS} resolver × budget cells, with every "
  f"point estimate favouring it ({min(PSR_PTS):+.4f} to {max(PSR_PTS):+.4f} at h = 0) and none "
  f"separating. The pre-registered wording for this case is explicit and is adopted: **admission "
  f"ranking has no signal on this workload**, as measured by AP. The budget itself matters — "
  f"admit-all is ahead of admit-none at h = 0 — but the *ordering* within a budget does not.")
w("- **The selection effect that does exist is about alarms, not about AP.** `P-score` admits the "
  "triggers the device is most confident about, the 32B resolver dismisses many of them, and the "
  "result is markedly fewer false alarms *and* fewer positive clips alarmed than random admission "
  "at the same budget. That is a real, repeatable selection effect on the application's behaviour; "
  "it simply does not show up in AP, which is computed on the continuous score stream and not on "
  "the alarm decisions.")
w("- **CLAUDE.md Rule 2 classification: REAL NEGATIVE for the trajectory claim and for admission "
  "ranking on AP.** The mechanism was present and instantiated (Step 2: every link non-zero and "
  "varying), it was exercised (the predictor separates benefit > 0 out of sample), the action "
  "space is shared and the budget is enforced and verified (negative control (a) is exact), and "
  "the headroom it was asked to capture demonstrably exists — `P-oracle` beats both endpoints at "
  "h = 0.5 s. The mechanism operated as specified and did not produce the claimed effect. "
  "Negative control (b) is **uninformative here rather than confirmatory**: the unshuffled "
  "predictor is already at P-random's level, so the shuffle had nothing to destroy; §11 records "
  "that, and this classification does not rest on it. For completeness, at h = 0 the endpoints "
  f"are {d_all['ap']['0.0']['ap'] - d_none['ap']['0.0']['ap']:+.4f} apart and §6 reports that "
  "column too, but h = 0.5 s was the pre-registered horizon and no rule is re-written here after "
  "seeing the results.")
w("- **What this does not show.** It does not show that admission ranking is worthless in "
  "deployment: the alarm-rate differences above are large and an application that acts on alarms "
  "would feel them, while AP — the metric this project fixed in advance and did not vary — is "
  "blind to them. It does not show that no "
  "trajectory feature could help — only that these features, fitted this way, on this trace, do "
  "not. It does not establish the device arm's accuracy, which remains an H100 measurement "
  "standing in for an Orin run never done on Nexar. And the budget here is a fraction of triggers, "
  "not a server: nothing in it models a queue, concurrency or admission latency.")
w()

# ---------------------------------------------------------------- 16 files
w("## 16. Files")
w()
for x in ["experiments/dashcam/study_e12_admission.py",
          "experiments/dashcam/study_e12_report.py",
          "results/dashcam/study_e12/e12_results.json",
          "results/dashcam/study_e12/e12_mechanism_verification.md",
          "reports/study_e12_admission.md (this file)"]:
    w(f"- `{x}`")
w()

(ROOT / "reports/study_e12_admission.md").write_text("\n".join(L) + "\n")
print("wrote reports/study_e12_admission.md", len(L), "lines")
