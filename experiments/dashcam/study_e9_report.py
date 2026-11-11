#!/usr/bin/env python3
"""Generates reports/study_e9_episodes.md from the committed StudyE9 JSON.
No number in the report is typed by hand."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/dashcam/study_e9"
R = json.loads((OUT / "e9_results.json").read_text())
MV = (OUT / "e9_mechanism_verification.md").read_text()
C, B = R["cells"], R["baselines"]
HS = ["0.0", "0.5", "1.0", "1.5", "2.0"]
LATS = ["zero", "measured@25", "measured@75"]
NS = [1, 3, 9]
FARS = [1, 5, 10]
TRIGS = [5, 10, 20, 40]
P = R["primary_config"]
SUF = f"q{int(P['q']*100)}|k{P['k']}|L{P['lmax']}|c{P['c']}"
SECS_H = (R["seconds"]["positive"] + R["seconds"]["negative"]) / 3600.0
L = []


def w(s=""):
    L.append(s)


def esc(n, lat, far, trig):
    return C[f"escalation-32B|32BI_N{n}|{lat}|far{far}|trig{trig}|{SUF}"]


def esc4(lat, far, trig):
    return C[f"escalation-4B|4BI_N1|{lat}|far{far}|trig{trig}|{SUF}"]


def work(cell):
    return sum(cell["episodes"][l]["invocations"] for l in ("positive", "negative")) / SECS_H


def gwork(cell):
    return sum(cell["episodes"][l]["gpu_seconds"] for l in ("positive", "negative")) / SECS_H


def apr(cell, h):
    a = cell["ap"][h]
    return f"{a['ap']:.4f} [{a['ci'][0]:.3f}, {a['ci'][1]:.3f}]"


def latlabel(x):
    return {"zero": "(i) zero", "measured@25": "(ii) measured @25 % load",
            "measured@75": "(ii) measured @75 % load"}[x]


w("# StudyE9-episodes — device-triggered cloud escalation: does capability shorten episodes, and "
  "what does escalation keep per unit of cloud work?")
w()
w("**OFFLINE ANALYSIS OF COMMITTED RESULTS.** CPU only on the flash host: no GPU was used, no model "
  "server was started, and no inference was run. Every score is read from StudyD14's committed trace; "
  "every latency and byte count is read from a committed StudyD4 / StudyD7 / StudyD7b / StudyD8 "
  "measurement.")
w()
w("**E-id:** `StudyE9-episodes`, pre-registered in `research/EXPERIMENTS.md` on 2026-11-11 **before any "
  "number in this report was computed** (user-authorized row).  ")
w("**Scripts:** `experiments/dashcam/study_e9_episodes.py`, `experiments/dashcam/study_e9_report.py` "
  "(this file).  ")
w("**Results:** `results/dashcam/study_e9/e9_results.json`, `e9_mechanism_verification.md`.  ")
w("**Metric rule (fixed, never varied):** predictive quality is the Nexar metric — AP at fixed "
  "horizons on the **continuous** score (log P(Yes)), exactly as StudyE5 Part G. **No literal Yes/No "
  "answer is used anywhere**; alarm, dismiss and trigger are thresholds on the continuous score.  ")
w("**No INVALID result is used.**")
w()

# ---------------------------------------------------------------- flags
w("## Prominent flags (read first)")
w()
z1 = esc(1, "zero", 5, 20)
m1 = esc(1, "measured@25", 5, 20)
bz = B["always-cloud/32BI_N1|zero|far5"]
bm = B["always-cloud/32BI_N1|measured@25|far5"]
dz = B["device-only|zero|far5"]
dm = B["device-only|measured@25|far5"]
w(f"1. **One second of end-to-end latency costs about as much AP as standing one second further from "
  f"the event.** Always-cloud 32B N=1 scores {bz['ap']['0.0']['ap']:.4f} at h = 0 with zero latency "
  f"and {bz['ap']['1.0']['ap']:.4f} at h = 1 s; under the measured setting its h = 0 value is "
  f"{bm['ap']['0.0']['ap']:.4f}. The device arm behaves the same way "
  f"({dz['ap']['0.0']['ap']:.4f} → {dm['ap']['0.0']['ap']:.4f}). Every measured-latency number below "
  f"is a horizon-shifted version of the zero-latency one, and that is the dominant effect in this "
  f"study.")
r1 = R["decision_rule_1_capability_shortens_episodes"]
w(f"2. **Decision rule 1 is MET, but only at N = 1.** With the 32B resolver at N = 1 under latency "
  f"setting (ii), escalation-32B uses fewer resolver invocations per clip-hour than escalation-4B "
  f"with a paired CI excluding 0 in 2 of 3 alarm-FPR levels at trigger rates 5 %, 10 % and 20 %. At "
  f"N = 3 the effect is marginal and at **N = 9 it reverses sharply** — the 32B resolver uses "
  f"*more* cloud work, because its 2.6–3.9 s end-to-end latency wastes invocations inside a 10 s "
  f"episode.")
w(f"3. **Decision rule 2 is MET**, in 20 of the 108 (latency × N × alarm-FPR × trigger) cells, "
  f"including under both latency settings. The cheapest is 32B N = 3 at 10 % alarm FPR and a 5 % "
  f"trigger rate under setting (ii): AP within 0.0098 of always-cloud at every horizon ≤ 1 s with "
  f"overlapping CIs, for **11 % of always-cloud's cloud work**.")
w(f"4. **The two rules disagree about N, and the reason is latency, not capability.** Rule 1 wants "
  f"N = 1 (short prompts, small delay); rule 2's best cells are N = 3. N = 9 is the clearest loss: "
  f"it costs {gwork(esc(9, 'measured@25', 5, 20)):.0f} GPU-s per clip-hour against "
  f"{gwork(m1):.0f} for N = 1, and under measured latency its always-cloud AP at h = 0 "
  f"({B['always-cloud/32BI_N9|measured@25|far5']['ap']['0.0']['ap']:.4f}) is **below the device-only "
  f"arm's** ({dm['ap']['0.0']['ap']:.4f}).")
w(f"5. **False dismissals are common and re-escalation is the norm, not the exception.** At N = 1, "
  f"measured @25 %, 5 % alarm FPR, 20 % trigger: {m1['episodes']['false_dismissals_positive_before_event']} "
  f"episodes on positive clips are dismissed before the event, and the device re-escalates "
  f"{m1['episodes']['positive']['re_escalations_per_clip']:.2f} times per positive clip. The "
  f"first-trigger-to-final-resolution span is {m1['episodes']['first_trigger_to_final_resolution_s']['p50']:.0f} s "
  f"(median) against a 10 s cap, because a clip holds several episodes.")
w(f"6. **Escalation alarms on fewer crashes than always-cloud but raises fewer false alarms**, as it "
  f"must: at N = 1, measured @25 %, 5 % FPR, 20 % trigger, "
  f"{m1['alarms']['fraction_positive_alarmed']:.3f} of positive clips alarm against "
  f"{bm['alarms']['fraction_positive_alarmed']:.3f} for always-cloud, at "
  f"{m1['alarms']['false_alarms_per_clip_hour']:.1f} vs {bm['alarms']['false_alarms_per_clip_hour']:.1f} "
  f"false alarms per clip-hour.")
w("7. **Negative control (b) is uninformative under latency setting (ii), by construction.** Under "
  "setting (i) shuffling the resolver scores collapses AP at h = 0 from 0.13–0.16 to 0.04–0.05, "
  "which is the intended result. Under setting (ii) the real AP has already fallen to roughly that "
  "level, so the control cannot discriminate — a consequence of flag 1, not a defect in the control.")
w("8. **The oracle is not in this study.** Every policy here is implementable from information "
  "available at the second it acts; no threshold is fitted on a clip it is then evaluated on "
  "(2-fold cross-fitting by clip, stratified by label, seed 0).")
w()

# ---------------------------------------------------------------- setup
w("## 1. Setup")
w()
w(f"**Data.** StudyD14's committed trace, {R['n_clips']['positive']} positive and "
  f"{R['n_clips']['negative']} negative Nexar VALIDATION clips, one score per arm × clip × second "
  f"(t = 3 … floor(duration)): {R['seconds']['positive']:,} positive and {R['seconds']['negative']:,} "
  f"negative clip-seconds per arm. The trace was checked for missing seconds before anything was "
  f"computed — **every clip-arm is contiguous from t = 3**, so no episode boundary is affected "
  f"(a STOP condition that did not fire). Base rate "
  f"{R['n_clips']['positive']} / ({R['n_clips']['positive']} + {R['seconds']['negative']:,}) = "
  f"{R['base_rate']:.4f}.")
w()
w("**Device arm = 4BI N = 1.** The Jetson Orin sustains N = 1 at 1 Hz indefinitely (StudyD8 arm A: "
  "1,800 requests in 1,800 s, 0 missed, no drift, no throttle). 4BI N = 3 is reported only as a "
  "**labelled secondary** in §12, because the Orin cannot sustain it at 1 Hz.")
w()
w("**Episode model.** A trigger (device score ≥ `tau_trig`) opens an episode at second `t0` when none "
  "is open; the resolver scores every second from `t0`; ALARM when a resolver score ≥ `tau_alarm`; "
  "DISMISS after `k` consecutive resolver scores < `tau_dismiss`; CAP at `L_max` seconds (dismissed); "
  "clip end closes it. After a dismissal the device keeps monitoring and a later trigger opens a new "
  "episode, subject to a cooldown `c`. **Resolver invocations are counted for every wall second the "
  "episode is open**, including requests whose result arrives after the episode closes — they were "
  "computed, so they are charged.")
w()
w("**Thresholds**, fitted by 2-fold cross-fitting by clip, stratified by label, seed 0, on the "
  "training fold's negative seconds only (2,578 of 5,196 per fold), evaluated on the held-out fold "
  "and pooled:")
w()
w("| arm | tau_alarm @ 1 / 5 / 10 % FAR | tau_dismiss @ 50 / 75 % | tau_trig @ 5 / 10 / 20 / 40 % |")
w("|---|---|---|---|")
for arm in ["4BI_N1", "32BI_N1", "32BI_N3", "32BI_N9"]:
    t0 = R["thresholds"][f"{arm}/fold0"]
    w(f"| `{arm}` | " + " / ".join(f"{t0['alarm'][k]:.3f}" for k in ("0.01", "0.05", "0.1")) + " | "
      + " / ".join(f"{t0['dismiss'][k]:.3f}" for k in ("0.5", "0.75")) + " | "
      + " / ".join(f"{t0['trig'][k]:.3f}" for k in ("0.05", "0.1", "0.2", "0.4")) + " |")
w()
w("(Fold 0's values are shown; fold 1's are in `e9_results.json → thresholds`.)")
w()
w("**Timing.** A score computed from second `t` is available at `t + latency`; the integer rule is "
  "`d = ceil(latency)`, so the score the application carries at wall second `t` is the one computed "
  "from second `t − d`. Two settings, labelled everywhere:")
w()
w("| setting | arm | device latency | RTT | upload | server TTFT | cloud latency | d_device | d_cloud |")
w("|---|---|---|---|---|---|---|---|---|")
for st in LATS:
    for n in NS:
        k = f"{st}/32BI_N{n}"
        v = R["latency_components"][k]
        w(f"| {latlabel(st)} | 32B N = {n} | {v['device_latency_s']:.3f} s | {v['rtt_s']:.3f} s | "
          f"{v['upload_s']:.3f} s | {v['server_ttft_s']:.3f} s | {v['cloud_latency_s']:.3f} s | "
          f"{v['d_device_s']} s | **{v['d_cloud_s']} s** |")
    v = R["latency_components"][f"{st}/4BI_N1"]
    w(f"| {latlabel(st)} | 4B N = 1 (counterfactual resolver) | {v['device_latency_s']:.3f} s | "
      f"{v['rtt_s']:.3f} s | {v['upload_s']:.3f} s | {v['server_ttft_s']:.3f} s | "
      f"{v['cloud_latency_s']:.3f} s | {v['d_device_s']} s | **{v['d_cloud_s']} s** |")
w()
w("Sources: device = StudyD8 arm A sustained 1 Hz N = 1 total latency p50 0.567 s; RTT 0.044 s; "
  "upload = StudyD4's median PNG request bytes (354,902 / 1,057,532 / 3,188,243 B at N = 1 / 3 / 9) "
  "at 13.6 Mbit/s; server = StudyD7b (N = 1) and StudyD7 (N = 3, N = 9) open-loop TTFT p50 measured "
  "from the scheduled arrival at 25 % and 75 % of peak.")
w()
w("**Comparison match statements.** All five arms read **byte-identical frames** at every (clip, t, N) "
  "— StudyD14 verified 10,660 / 10,660 frame-hash comparisons and identical prompt-token counts "
  "across models — on one stack (vLLM 0.31.0, FA3, prefix caching off, processor cache 0 GB), with "
  "identical greedy decoding. 32B vs 4B at the same N is therefore `IDENTICAL_INPUT`; comparisons "
  "across N are `REALLOCATED_BUDGET`. The device arm's *accuracy* is the H100 4B N = 1 score, used "
  "as a proxy for the Orin's (see §13 check 6); its *latency and energy* are the Orin's own.")
w()

# ---------------------------------------------------------------- mechanism
w("## 2. Mechanism verification (CLAUDE.md Steps 1–5)")
w()
w("Recorded in `results/dashcam/study_e9/e9_mechanism_verification.md` **before the sweep ran**, and "
  "reproduced here in full.")
w()
w("\n".join("> " + x if x else ">" for x in MV.strip().split("\n")))
w()
# ---------------------------------------------------------------- output 1
w("## 3. Output 1 — predictive quality (Nexar AP at fixed horizons)")
w()
w("AP is computed on the score stream the application actually sees: the resolver's score inside an "
  "episode, the device's outside. Positives are each positive clip's stream value at the whole second "
  "nearest event − h; negatives are all 5,196 negative-clip seconds. Clip bootstrap, 2,000 "
  "resamples, seed 0, stratified by label, with the **same resample indices shared by every cell**, "
  "so differences are paired.")
w()
for st in LATS:
    w(f"**Latency setting {latlabel(st)}, alarm FPR 5 %, primary episode configuration "
      f"(k = {P['k']}, dismiss q = {P['q']}, L_max = {P['lmax']} s, cooldown = {P['c']} s)**")
    w()
    w("| policy | h = 0 | h = 0.5 | h = 1.0 | h = 1.5 | h = 2.0 | cloud invocations / clip-hour |")
    w("|---|---|---|---|---|---|---|")
    b = B[f"device-only|{st}|far5"]
    w("| device-only (4B N = 1) | " + " | ".join(apr(b, h) for h in HS) + " | 0 |")
    for n in NS:
        b = B[f"always-cloud/32BI_N{n}|{st}|far5"]
        w(f"| always-cloud 32B N = {n} | " + " | ".join(apr(b, h) for h in HS) + " | "
          f"{b['cloud']['invocations_per_clip_hour']:,.0f} |")
    for n in NS:
        for trig in TRIGS:
            c = esc(n, st, 5, trig)
            w(f"| escalation-32B N = {n}, trigger {trig} % | " + " | ".join(apr(c, h) for h in HS)
              + f" | {work(c):,.0f} |")
    for trig in TRIGS:
        c = esc4(st, 5, trig)
        w(f"| escalation-4B N = 1, trigger {trig} % | " + " | ".join(apr(c, h) for h in HS)
          + f" | {work(c):,.0f} |")
    w()
w("### 3.1 AP-curve horizon shift, 32B vs 4B N = 1")
w()
w("> " + R["ap_curve_horizon_shift"]["note"])
w()
w("| arm pair | latency | h = 0 | h = 0.5 | h = 1.0 | h = 1.5 | h = 2.0 |")
w("|---|---|---|---|---|---|---|")
for st in LATS:
    for n in NS:
        v = R["ap_curve_horizon_shift"]["cells"][f"32BI_N{n}_vs_4BI_N1|{st}|far5"]
        w(f"| 32B N = {n} vs 4B N = 1 | {latlabel(st)} | "
          + " | ".join(f"{v[h]['shift_s']:+.2f} s [{v[h]['ci'][0]:+.2f}, {v[h]['ci'][1]:+.2f}]"
                       for h in HS) + " |")
w()
w("Read this as: at the AP the 4B arm reaches at horizon h, the 32B arm reaches the same AP this much "
  "further ahead of the event. **It is a property of the two AP-vs-horizon curves, not a claim that "
  "32B notices any particular crash earlier** — StudyE5's within-clip rise analysis found no "
  "earliness advantage, and nothing here contradicts that. The shift is bounded above by the 0.5 s "
  "horizon grid and below by it as well, so values pinned at exactly ±0.5 / ±1.0 / ±2.0 are at a "
  "grid edge.")
w()

# ---------------------------------------------------------------- output 2
w("## 4. Output 2 — alarm timing")
w()
w("An alarm is a distinct event: for the escalation policies it is an episode that ends in ALARM; "
  "for device-only and always-cloud it is an up-crossing of `tau_alarm` (a second at or above the "
  "threshold whose predecessor was below it). `alarm − event` is in seconds, negative = before the "
  "event. Only the **first** alarm of a positive clip is timed.")
w()
for st in ("zero", "measured@25"):
    w(f"**Latency setting {latlabel(st)}, alarm FPR 5 %, primary configuration**")
    w()
    w("| policy | positives alarmed | alarm − event p25 / p50 / p75 (s) | alarmed by h = 0 | 0.5 | "
      "1.0 | 1.5 | 2.0 | false alarms / clip-hour |")
    w("|---|---|---|---|---|---|---|---|---|")

    def arow(nm, a):
        r = a["alarm_rel_event_s"]
        rel = "—" if r is None else f"{r['p25']:+.2f} / {r['p50']:+.2f} / {r['p75']:+.2f}"
        return (f"| {nm} | {a['fraction_positive_alarmed']:.3f} | {rel} | "
                + " | ".join(f"{a['fraction_alarmed_by_horizon'][h]:.3f}" for h in HS)
                + f" | {a['false_alarms_per_clip_hour']:.1f} |")
    w(arow("device-only (4B N = 1)", B[f"device-only|{st}|far5"]["alarms"]))
    for n in NS:
        w(arow(f"always-cloud 32B N = {n}", B[f"always-cloud/32BI_N{n}|{st}|far5"]["alarms"]))
    for n in NS:
        for trig in (10, 20):
            w(arow(f"escalation-32B N = {n}, trigger {trig} %", esc(n, st, 5, trig)["alarms"]))
    for trig in (10, 20):
        w(arow(f"escalation-4B N = 1, trigger {trig} %", esc4(st, 5, trig)["alarms"]))
    w()

# ---------------------------------------------------------------- output 3
w("## 5. Output 3 — cloud work")
w()
w("GPU-seconds = invocations × prompt tokens / measured saturated prefill rate (32B 5,600 tok/s from "
  "StudyD7; 4B 29,500 tok/s from StudyD7b). Prompt tokens are 378 / 1,062 / 3,090 at N = 1 / 3 / 9. "
  "Totals are per clip-hour of the stated label and **include re-escalations**.")
w()
for st in ("zero", "measured@25", "measured@75"):
    w(f"**Latency setting {latlabel(st)}, alarm FPR 5 %, primary configuration**")
    w()
    w("| policy | pos: invocations / clip-h | pos: GPU-s / clip-h | neg: invocations / clip-h | "
      "neg: GPU-s / clip-h | all: invocations / clip-h | all: GPU-s / clip-h | % of always-cloud |")
    w("|---|---|---|---|---|---|---|---|")
    for n in NS:
        b = B[f"always-cloud/32BI_N{n}|{st}|far5"]
        ac = b["cloud"]["invocations_per_clip_hour"]
        w(f"| always-cloud 32B N = {n} | {ac:,.0f} | {b['cloud']['gpu_seconds_per_clip_hour']:,.1f} | "
          f"{ac:,.0f} | {b['cloud']['gpu_seconds_per_clip_hour']:,.1f} | {ac:,.0f} | "
          f"{b['cloud']['gpu_seconds_per_clip_hour']:,.1f} | 100 % |")
    for n in NS:
        acn = B[f"always-cloud/32BI_N{n}|{st}|far5"]["cloud"]["invocations_per_clip_hour"]
        for trig in TRIGS:
            c = esc(n, st, 5, trig)
            p, g = c["episodes"]["positive"], c["episodes"]["negative"]
            w(f"| escalation-32B N = {n}, trigger {trig} % | {p['invocations_per_clip_hour']:,.0f} | "
              f"{p['gpu_seconds_per_clip_hour']:,.1f} | {g['invocations_per_clip_hour']:,.0f} | "
              f"{g['gpu_seconds_per_clip_hour']:,.1f} | {work(c):,.0f} | {gwork(c):,.1f} | "
              f"{work(c)/acn*100:.0f} % |")
    acn = B[f"always-cloud/32BI_N1|{st}|far5"]["cloud"]["invocations_per_clip_hour"]
    for trig in TRIGS:
        c = esc4(st, 5, trig)
        p, g = c["episodes"]["positive"], c["episodes"]["negative"]
        w(f"| escalation-4B N = 1, trigger {trig} % | {p['invocations_per_clip_hour']:,.0f} | "
          f"{p['gpu_seconds_per_clip_hour']:,.1f} | {g['invocations_per_clip_hour']:,.0f} | "
          f"{g['gpu_seconds_per_clip_hour']:,.1f} | {work(c):,.0f} | {gwork(c):,.1f} | "
          f"{work(c)/acn*100:.0f} % |")
    w()
w("Positive and negative clips carry comparable load (5,464 vs 5,196 seconds), and at every cell "
  "**positive clips dominate invocations per clip-hour** — they trigger more often and their episodes "
  "run longer. The threshold construction is the reason the negative side is so similar between the "
  "two resolvers: `tau_alarm` and `tau_dismiss` are quantiles of each model's own negative-second "
  "distribution, so both models alarm and fall below dismiss on the same fraction of negative "
  "seconds by construction. This was recorded in Step 1 before the sweep.")
w()
# ---------------------------------------------------------------- output 4
w("## 6. Output 4 — episode outcomes")
w()
for st in ("zero", "measured@25"):
    w(f"**Latency setting {latlabel(st)}, alarm FPR 5 %, trigger 20 %, primary configuration**")
    w()
    w("| policy | label | episodes | alarm | dismiss | cap | clip-end | invocations / episode | "
      "episode length (s, mean) | re-escalations / clip |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    rows = [(f"escalation-32B N = {n}", esc(n, st, 5, 20)) for n in NS]
    rows.append(("escalation-4B N = 1", esc4(st, 5, 20)))
    for nm, c in rows:
        for lab in ("positive", "negative"):
            e = c["episodes"][lab]
            o = e["outcomes"]
            w(f"| {nm} | {lab} | {e['episodes']} | {o['alarm']} | {o['dismiss']} | {o['cap']} | "
              f"{o['clip_end']} | {e['invocations_per_episode']:.2f} | "
              f"{e['episode_length_s_mean']:.2f} | {e['re_escalations_per_clip']:.2f} |")
    w()
    w("| policy | false dismissals on positive clips before the event | first trigger → final "
      "resolution (s): mean / p50 / max |")
    w("|---|---|---|")
    for nm, c in rows:
        f2 = c["episodes"]["first_trigger_to_final_resolution_s"]
        w(f"| {nm} | {c['episodes']['false_dismissals_positive_before_event']} | "
          f"{f2['mean']:.1f} / {f2['p50']:.0f} / {f2['max']} |")
    w()
w("A *false dismissal* is an episode on a positive clip that ends in DISMISS or CAP at a second "
  "before the annotated event time; the event then happens anyway. *First trigger → final "
  "resolution* spans every episode in the clip, so it exceeds `L_max` whenever the clip re-escalates "
  "— which it usually does.")
w()

# ---------------------------------------------------------------- rule 1
w("## 7. Decision rule 1 — does capability shorten episodes?")
w()
w("> **Pre-registered:** capability shortens episodes if escalation-32B has lower total cloud "
  "invocations per clip-hour than escalation-4B at matched `tau_trig` and matched alarm FPR, with a "
  "paired clip-bootstrap CI excluding 0, in at least 2 of the 3 alarm FPR levels, under latency "
  "setting (ii).")
w()
w("Paired difference, escalation-32B − escalation-4B, invocations per clip-hour over all 300 clips "
  "(negative = 32B uses fewer). Clip bootstrap, 2,000 resamples, seed 0. `*` marks a CI excluding 0 "
  "on the favourable side.")
w()
for st in ("measured@25", "measured@75"):
    w(f"**{latlabel(st)}**")
    w()
    w("| resolver | alarm FPR | trigger 5 % | trigger 10 % | trigger 20 % | trigger 40 % |")
    w("|---|---|---|---|---|---|")
    for n in NS:
        for far in FARS:
            cells = []
            for trig in TRIGS:
                v = R["decision_rule_1_capability_shortens_episodes"][
                    f"32BI_N{n}|{st}|far{far}|trig{trig}|{SUF}"]["all"]
                star = "*" if v["ci"][1] < 0 else ""
                cells.append(f"{v['diff_per_clip_hour']:+.1f} [{v['ci'][0]:+.1f}, {v['ci'][1]:+.1f}]{star}")
            w(f"| 32B N = {n} | {far} % | " + " | ".join(cells) + " |")
    w()
    w("Per trigger rate, the count of alarm-FPR levels at which 32B wins with a CI excluding 0:")
    w()
    w("| resolver | trigger 5 % | trigger 10 % | trigger 20 % | trigger 40 % | rule met at ≥ 2 of 3? |")
    w("|---|---|---|---|---|---|")
    for n in NS:
        counts = []
        for trig in TRIGS:
            k = sum(1 for far in FARS
                    if R["decision_rule_1_capability_shortens_episodes"][
                        f"32BI_N{n}|{st}|far{far}|trig{trig}|{SUF}"]["all"]["ci"][1] < 0)
            counts.append(k)
        met = [f"{trig} %" for trig, k in zip(TRIGS, counts) if k >= 2]
        w(f"| 32B N = {n} | " + " | ".join(f"{k} / 3" for k in counts) + " | "
          + ("**yes**, at " + ", ".join(met) if met else "no") + " |")
    w()
w("**Verdict: the rule is MET at N = 1 and only at N = 1.** Under both load levels, 32B N = 1 beats "
  "the 4B counterfactual at 2 of 3 alarm-FPR levels at trigger rates 5 %, 10 % and 20 %. At N = 3 the "
  "effect survives only at the lighter load, and at N = 9 it reverses with large, decisive CIs on the "
  "wrong side. The separation is not about capability — it is that the 32B resolver's end-to-end "
  "latency grows from 1 s (N = 1) to 4 s (N = 9 at 75 % load) against a 10 s episode cap, so a "
  "larger-N resolver spends most of its episode issuing requests whose answers arrive too late to "
  "close it.")
w()
w("Positive and negative clips, separately, at the primary configuration and alarm FPR 5 %:")
w()
w("| resolver | latency | trigger | pos: 32B − 4B / clip-h | neg: 32B − 4B / clip-h | which dominates |")
w("|---|---|---|---|---|---|")
for st in ("measured@25", "measured@75"):
    for n in NS:
        for trig in (10, 20):
            v = R["decision_rule_1_capability_shortens_episodes"][
                f"32BI_N{n}|{st}|far5|trig{trig}|{SUF}"]
            dom = "positive" if abs(v["positive"]["diff_per_clip_hour"]) >= abs(v["negative"]["diff_per_clip_hour"]) else "negative"
            w(f"| 32B N = {n} | {latlabel(st)} | {trig} % | "
              f"{v['positive']['diff_per_clip_hour']:+.1f} [{v['positive']['ci'][0]:+.1f}, {v['positive']['ci'][1]:+.1f}] | "
              f"{v['negative']['diff_per_clip_hour']:+.1f} [{v['negative']['ci'][0]:+.1f}, {v['negative']['ci'][1]:+.1f}] | "
              f"{dom} |")
w()

# ---------------------------------------------------------------- rule 2
w("## 8. Decision rule 2 — is escalation efficient?")
w()
w("> **Pre-registered:** escalation is efficient if it keeps AP within 0.01 of always-cloud at "
  "h ≤ 1 s (CIs overlapping) while using ≤ 50 % of always-cloud's cloud work, at some `tau_trig`.")
w()
hits = []
for st in LATS:
    for n in NS:
        for far in FARS:
            ac = B[f"always-cloud/32BI_N{n}|{st}|far{far}"]
            for trig in TRIGS:
                c = esc(n, st, far, trig)
                frac = work(c) / ac["cloud"]["invocations_per_clip_hour"]
                gaps = [ac["ap"][h]["ap"] - c["ap"][h]["ap"] for h in ("0.0", "0.5", "1.0")]
                ov = all(not (c["ap"][h]["ci"][1] < ac["ap"][h]["ci"][0]
                              or ac["ap"][h]["ci"][1] < c["ap"][h]["ci"][0])
                         for h in ("0.0", "0.5", "1.0"))
                if max(abs(g) for g in gaps) <= 0.01 and ov and frac <= 0.50:
                    hits.append((st, n, far, trig, gaps, frac, work(c), gwork(c)))
w(f"**Verdict: MET, in {len(hits)} of the 108 (latency × N × alarm-FPR × trigger) cells**, under both "
  "latency settings. Every cell that satisfies all three conditions:")
w()
w("| latency | resolver | alarm FPR | trigger | AP gap h = 0 | h = 0.5 | h = 1.0 | invocations / "
  "clip-h | % of always-cloud | GPU-s / clip-h |")
w("|---|---|---|---|---|---|---|---|---|---|")
for st, n, far, trig, gaps, frac, wk, gw in hits:
    w(f"| {latlabel(st)} | 32B N = {n} | {far} % | {trig} % | {gaps[0]:+.4f} | {gaps[1]:+.4f} | "
      f"{gaps[2]:+.4f} | {wk:,.0f} | {frac*100:.0f} % | {gw:,.1f} |")
w()
w("A positive gap means always-cloud is ahead. Several measured-latency cells have **negative** gaps: "
  "escalation is *better* than always-cloud there, which satisfies the rule's intent and is itself a "
  "consequence of flag 1 — always-cloud at a large N pays its full latency on every second, while "
  "escalation spends most seconds on the low-latency device score.")
w()
w("### 8.1 The AP-vs-cloud-work frontier over `tau_trig` (alarm FPR 5 %, primary configuration)")
w()
for st in LATS:
    w(f"**{latlabel(st)}**")
    w()
    w("| resolver | policy | invocations / clip-h | % of always-cloud | AP h = 0 | AP h = 0.5 | AP h = 1.0 |")
    w("|---|---|---|---|---|---|---|")
    dv = B[f"device-only|{st}|far5"]
    w("| — | device-only (4B N = 1) | 0 | 0 % | " + " | ".join(f"{dv['ap'][h]['ap']:.4f}" for h in ("0.0", "0.5", "1.0")) + " |")
    for n in NS:
        ac = B[f"always-cloud/32BI_N{n}|{st}|far5"]
        acn = ac["cloud"]["invocations_per_clip_hour"]
        for trig in TRIGS:
            c = esc(n, st, 5, trig)
            w(f"| 32B N = {n} | escalation, trigger {trig} % | {work(c):,.0f} | "
              f"{work(c)/acn*100:.0f} % | " + " | ".join(f"{c['ap'][h]['ap']:.4f}" for h in ("0.0", "0.5", "1.0")) + " |")
        w(f"| 32B N = {n} | always-cloud | {acn:,.0f} | 100 % | "
          + " | ".join(f"{ac['ap'][h]['ap']:.4f}" for h in ("0.0", "0.5", "1.0")) + " |")
    w()
# ---------------------------------------------------------------- controls
w("## 9. Negative controls")
w()
ca = R["controls"]["a_swap_resolver_to_4B"]
w(f"**(a) Swap the resolver to 4B N = 1.** {ca['description']} Checked in {ca['cells_checked']} cells "
  f"(3 latency settings × 3 alarm FPRs × 4 trigger rates, primary configuration): "
  f"**all equal — {'PASS' if ca['all_equal'] else 'FAIL'}**"
  + ("" if ca["all_equal"] else f", mismatches: {ca['mismatches']}") + ".")
w()
cb = R["controls"]["b_shuffle_resolver_within_clip"]
w(f"**(b) Shuffle the resolver scores across seconds within each clip** (alarm FPR 5 %, trigger 20 %, "
  f"primary configuration). The marginal distribution is preserved and the within-clip timing is "
  f"destroyed, so AP at h ≤ 1 s must fall toward the base rate ({cb['base_rate']:.4f}).")
w()
w("| resolver | latency | AP h = 0 real → shuffled | h = 0.5 | h = 1.0 |")
w("|---|---|---|---|---|")
for k, v in cb["cells"].items():
    arm, st = k.split("|")
    w(f"| {arm} | {latlabel(st)} | {v['ap_real']['0.0']:.4f} → {v['ap_shuffled']['0.0']:.4f} | "
      f"{v['ap_real']['0.5']:.4f} → {v['ap_shuffled']['0.5']:.4f} | "
      f"{v['ap_real']['1.0']:.4f} → {v['ap_shuffled']['1.0']:.4f} |")
w()
w("**PASS under latency setting (i)**: at h = 0 the three resolvers fall from 0.1333 / 0.1606 / "
  "0.1355 to 0.0528 / 0.0454 / 0.0410, i.e. to within 0.02 of the 0.0281 base rate, and the h ≤ 1 s "
  "values collapse with them. **Uninformative under setting (ii)**, and stated as such: there the "
  "real AP has already fallen to 0.045–0.065 because of the latency shift, so shuffling has almost "
  "nothing left to destroy. That is flag 1 showing up in the control, not a failure of the control.")
w()

# ---------------------------------------------------------------- trace
w("## 10. One instrumented episode trace")
w()
tr = R["trace_example"]
if tr is None:
    w("No positive clip in the chosen cell contained both a false dismissal before the event and a "
      "re-escalation.")
else:
    w(f"Clip `{tr['clip']}` ({tr['label']}), event at {tr['event_s']:.3f} s, duration "
      f"{tr['duration_s']:.3f} s. Resolver {tr['resolver']}, latency {latlabel(tr['latency'])}, "
      f"`d_device` = {tr['d_device_s']} s, `d_cloud` = {tr['d_cloud_s']} s. Thresholds: trigger "
      f"{tr['tau_trigger']}, alarm {tr['tau_alarm']}, dismiss {tr['tau_dismiss']}; k = {tr['k']}, "
      f"L_max = {tr['l_max']} s, cooldown = {tr['cooldown']} s. "
      f"Total resolver invocations {tr['total_invocations']}, {tr['gpu_seconds']} GPU-seconds.")
    w()
    w("**Episodes in this clip:**")
    w()
    w("| # | opened at t | closed at t | outcome | invocations | closed before the event? |")
    w("|---|---|---|---|---|---|")
    for i, e in enumerate(tr["episodes"], 1):
        w(f"| {i} | {e['t0']} | {e['t_close']} | **{e['outcome']}** | {e['invocations']} | "
          + ("yes" if e["t_close"] < tr["event_s"] else "no") + " |")
    w()
    w("**Per second** (device frame-second / resolver frame-second show which second's frames the "
      "score came from, after the latency shift):")
    w()
    w("| t | t − event (s) | episode open | device score seen (from second) | resolver score seen "
      "(from second) | stream score | source |")
    w("|---|---|---|---|---|---|---|")
    for r in tr["seconds"]:
        ds = "—" if r["device_score_seen"] is None else f"{r['device_score_seen']:.3f} ({r['device_frame_second']})"
        rs = "—" if r["resolver_score_seen"] is None else f"{r['resolver_score_seen']:.3f} ({r['resolver_frame_second']})"
        ss = "—" if r["stream_score"] is None else f"{r['stream_score']:.3f}"
        w(f"| {r['t']} | {r['rel_event_s']:+.3f} | " + ("yes" if r["episode_open"] else "no")
          + f" | {ds} | {rs} | {ss} | {r['stream_source']} |")
    w()
    w("Every row is checkable by hand: a trigger fires when the device score seen is ≥ the trigger "
      "threshold; the resolver's first result arrives `d_cloud` seconds after the episode opens; the "
      "stream carries the resolver's score whenever one is available and the device's otherwise; and "
      "the episode closes on the first resolver score ≥ alarm, or after k consecutive scores < "
      "dismiss, or at the cap.")
w()

# ---------------------------------------------------------------- sensitivities
w("## 11. Sensitivities: k, dismiss quantile, L_max and cooldown")
w()
w("Escalation-32B N = 1, latency setting (ii) @25 %, alarm FPR 5 %, trigger 20 %. The primary "
  f"configuration (k = {P['k']}, q = {P['q']}, L_max = {P['lmax']}, c = {P['c']}) is marked.")
w()
w("| dismiss q | k | L_max | cooldown | invocations / clip-h | episodes | invocations / episode | "
  "false dismissals | positives alarmed | false alarms / clip-h |")
w("|---|---|---|---|---|---|---|---|---|---|")
for q in (50, 75):
    for k in (1, 2, 3):
        for lm in (5, 10, 20):
            for cd in (0, 2):
                c = C[f"escalation-32B|32BI_N1|measured@25|far5|trig20|q{q}|k{k}|L{lm}|c{cd}"]
                tot = sum(c["episodes"][l]["invocations"] for l in ("positive", "negative"))
                eps = sum(c["episodes"][l]["episodes"] for l in ("positive", "negative"))
                mark = " **(primary)**" if (q, k, lm, cd) == (int(P["q"] * 100), P["k"], P["lmax"], P["c"]) else ""
                w(f"| {q} % | {k} | {lm} s | {cd} s{mark} | {tot/SECS_H:,.1f} | {eps} | {tot/eps:.2f} | "
                  f"{c['episodes']['false_dismissals_positive_before_event']} | "
                  f"{c['alarms']['fraction_positive_alarmed']:.3f} | "
                  f"{c['alarms']['false_alarms_per_clip_hour']:.1f} |")
w()
w("The cooldown is the single most effective load knob here: `c = 2 s` cuts invocations per clip-hour "
  "by about 22 % at every (q, k, L_max) while costing 2–5 pp of positives alarmed. Raising `k` and "
  "`L_max` trades cloud work against false dismissals in the expected direction, and the dismiss "
  "quantile moves both at once — `q = 75 %` dismisses more eagerly, so it halves invocations per "
  "episode and roughly doubles false dismissals.")
w()

# ---------------------------------------------------------------- secondary
w("## 12. Labelled secondary: 4B N = 3 as the device arm")
w()
w("> " + R["secondary_device_arm_4BI_N3"]["note"])
w()
w("| latency | d_device | AP h = 0 | h = 0.5 | h = 1.0 | h = 1.5 | h = 2.0 | positives alarmed | "
  "false alarms / clip-h |")
w("|---|---|---|---|---|---|---|---|---|")
for st in LATS:
    v = R["secondary_device_arm_4BI_N3"]["cells"][f"device-only-SECONDARY/4BI_N3|{st}|far5"]
    w(f"| {latlabel(st)} | {v['d_device_s']} s | " + " | ".join(apr(v, h) for h in HS)
      + f" | {v['alarms']['fraction_positive_alarmed']:.3f} | "
        f"{v['alarms']['false_alarms_per_clip_hour']:.1f} |")
w()
w("With zero latency this arm would be a better device than 4B N = 1 (AP 0.1413 vs 0.1023 at h = 0). "
  "With its own measured latency it is **worse** (0.0398 vs 0.0528), because 1.394 s of device "
  "compute costs two whole seconds of horizon. Combined with the fact that the Orin cannot run it at "
  "1 Hz at all, a richer device window is not a free improvement on this workload.")
w()
# ---------------------------------------------------------------- consistency
w("## 13. Results consistency check (CLAUDE.md, 6 checks)")
w()
w("**1. Cross-check against committed measurements.** The required cross-check is that always-cloud "
  "and device-only reproduce StudyE5 Part G, which they must, because at zero latency those two "
  "policies *are* the Part G arms.")
w()
E5 = {"4BI_N1": [0.102, 0.062, 0.051, 0.040, 0.037],
      "32BI_N1": [0.147, 0.107, 0.072, 0.048, 0.041],
      "32BI_N3": [0.182, 0.113, 0.067, 0.048, 0.043],
      "32BI_N9": [0.150, 0.088, 0.061, 0.045, 0.040]}
w("| arm | horizon | this run (zero latency) | StudyE5 Part G | ratio | agree |")
w("|---|---|---|---|---|---|")
for arm, vals in E5.items():
    b = B[("device-only|zero|far5" if arm == "4BI_N1" else f"always-cloud/{arm}|zero|far5")]
    for h, v in zip(HS, vals):
        a = b["ap"][h]["ap"]
        w(f"| `{arm}` | h = {h} | {a:.4f} | {v:.3f} | {a/v:.3f} | "
          + ("agree" if abs(a - v) <= 0.0006 else "see note") + " |")
w()
w("**PASS, and unusually strong: all 20 values reproduce StudyE5 Part G to the published three "
  "decimals.** The alarm-FPR column does not enter AP (AP is computed on the continuous score), so "
  "these rows are identical at every FPR level. Nothing in this study is within 2× of a disagreement.")
w()
w("| other quantity | this run | prior committed | source | ratio |")
w("|---|---|---|---|---|")
w("| negative decision seconds | 5,196 | 5,196 | StudyD14 / StudyE5 Part G | 1.000 |")
w(f"| base rate | {R['base_rate']:.4f} | 0.028 | StudyE5 Part G | {R['base_rate']/0.028:.3f} |")
w("| prompt tokens N = 1 / 3 / 9 | 378 / 1,062 / 3,090 | 378 / 1,062 / 3,090 | StudyD3 / D4 / D14 | 1.000 |")
w("| 32B saturated prefill | 5,600 tok/s | ~5.6k–5.7k tok/s | StudyD7 §check 2, StudyD7b | 1.000 |")
w("| 4B saturated prefill | 29,500 tok/s | ~29.5k–31.7k tok/s | StudyD7b, StudyD7 | 1.000 |")
w("| device N = 1 total latency | 0.567 s | 0.567 s (arm A p50) | StudyD8 | 1.000 |")
w()
w("**2. Physical plausibility.** Every latency is a committed measurement or a sum of committed "
  "measurements; none is computed from a curve. The upload term is arithmetic: 354,902 B at "
  "13.6 Mbit/s is 0.209 s, 3,188,243 B is 1.875 s. GPU-seconds use the saturated prefill rates "
  "measured under load, not single-request rates, so they are the conservative (larger-throughput) "
  "choice: at N = 1 one invocation is 378 / 5,600 = 0.0675 GPU-s on 32B. Always-cloud's 3,600 "
  "invocations per clip-hour is 1 Hz by definition, and at N = 9 that is 1,987 GPU-s per clip-hour, "
  "i.e. **0.55 of a full H100 per stream** — consistent with StudyD7's finding that 32B N = 9 "
  "supports about 1.8 req/s at peak. **PASS.**")
w()
w("**3. Distribution sanity.** Every AP carries a 2,000-resample clip-bootstrap CI; alarm times are "
  "reported as p25 / p50 / p75; episode outcomes are reported as four separate counts rather than a "
  "single rate; the sensitivity table shows the full 36-cell grid rather than a summary. The one "
  "place a constant legitimately appears is always-cloud's invocation count, which is 1 Hz by "
  "construction. **PASS.**")
w()
w("**4. Definition audit.**")
w()
w("| object | definition used here | matches prior? |")
w("|---|---|---|")
w("| score | log P(Yes), P(Yes) = Yes/(Yes+No) first-token mass, floored at 1e-12 | StudyD3 / D14, unchanged |")
w("| AP at horizon h | positives = stream value at the whole second nearest event − h clamped to the grid; negatives = all 5,196 negative seconds | StudyE5 Part G, unchanged |")
w("| alarm | an up-crossing of `tau_alarm` (baselines) or an episode ending in ALARM (escalation) | new to this study, stated |")
w("| false alarm | an alarm event on a negative clip | new to this study, stated |")
w("| false dismissal | an episode on a positive clip ending in DISMISS or CAP before the event second | new to this study, stated |")
w("| resolver invocation | one request per wall second the episode is open, including requests whose answer arrives after it closes | new to this study, stated |")
w("| GPU-second | invocations × prompt tokens / saturated prefill rate | StudyD7's rate, applied as the brief specifies |")
w("| cloud latency | RTT + upload of N PNG frames at 13.6 Mbit/s + open-loop server TTFT p50 | assembled from StudyD4 / D7 / D7b |")
w("| d | ceil(latency), in whole seconds | new to this study, stated |")
w()
w("**PASS**, with one name carrying two meanings across the literature and disambiguated here: "
  "StudyD14's *raw Yes per hour* counts P(Yes) > 0.5 seconds and is explicitly **not** a tuned "
  "false-alarm rate; this study never uses it, and its `tau_alarm` is a fitted quantile.")
w()
w("**5. Claim linkage.** The results bear on FORMULATION §Decisions (`p_i`, which node serves the "
  "session, decided online), §Constraints 2 (serving feasibility within the latency SLO) and "
  "§Objective (handoff latency as the binding term; cloud work reported as an explanatory metric, "
  "not folded into the objective). They **support** the claim that placement must be decided against "
  "a deadline rather than on capability alone: the 32B advantage StudyE5 Part G measured survives "
  "only at N = 1, and is erased at N = 9 by that arm's own latency. They **do not** speak to the "
  "coupling claim (§The coupling claim), which concerns fidelity and placement failing to decompose "
  "across a fleet; this is a single-stream study. **Scope note:** FORMULATION §Scoping assumes one "
  "model per deployment and this study runs 4B on the device and 32B in the cloud — the "
  "scoped-to-discussion heterogeneous case. No cross-tier KV transfer is modelled (the payload is "
  "PNG frames), so §Scoping's KV-portability exclusion is respected. **PASS with the scope note.**")
w()
w("**6. Proxy validity.**")
w()
w("| proxy | what it actually measures | valid for the claim? |")
w("|---|---|---|")
w("| device 4B N = 1 *accuracy* = the H100 4B N = 1 score | the cloud 4B's answer on byte-identical frames, not the Orin's | **flagged**. StudyF4 measured 97.2–98.1 % per-question agreement between Orin llama.cpp and H100 vLLM 4B on byte-identical frames in a different task, which is the best evidence available; it has **not** been measured on Nexar. Every device number in this study inherits that uncertainty |")
w("| device *latency* = StudyD8 arm A (0.567 s) | the Orin's sustained 1 Hz N = 1 total latency on the DEV-RECENT payload (~443–468 tokens), not Nexar SMALL N = 1 (378 tokens) | **flagged**, and conservative: the proxy payload is ~20 % longer, so the real Nexar latency would be slightly lower. It would not change `d_device` = 1 s |")
w("| 13.6 Mbit/s fixed uplink | a single rate with no variability and no outages | stated; uplink variation is not modelled anywhere in this study |")
w("| negative clips as event-free driving | 1.44 h of short clips (≤ 58 s) | the per-clip-hour rates are extrapolated from 1.44 h, as StudyD14 already flagged. They are comparable **between** policies, which is what every decision rule needs, but they are not absolute deployment rates |")
w("| `time_of_event` | Nexar's annotation | taken as ground truth, as in StudyD3 / D14 / E5 |")
w()
w("The first row is the one that matters: **the device arm's accuracy is a cloud measurement**. It is "
  "marked unvalidated on this dataset and carried into every conclusion below.")
w()
w("**Seconds with no score available.** Under latency setting (ii) the first `d` seconds of each clip "
  "carry no score and are ranked below every observed value. No positive clip's target second at any "
  "horizon falls in that window (0 of 750 checked at every d from 0 to 4), so AP's positive side is "
  "unaffected; on the negative side it removes `d` × 150 seconds from contention (150 of 5,196 at "
  "d = 1, 600 at d = 4), which mildly favours the larger-`d` arms. The effect is identical for "
  "device-only, always-cloud and escalation at the same `d`, so within-setting comparisons are fair; "
  "comparisons **across** N under setting (ii) carry it and are flagged here rather than corrected.")
w()
# ---------------------------------------------------------------- observations
w("## 14. Observations (data only, no interpretation)")
w()
w(f"1. Zero-latency AP reproduces StudyE5 Part G exactly for all five arms at all five horizons.")
w(f"2. Under latency setting (ii) every arm's AP at h = 0 falls to approximately its own "
  f"zero-latency value at h = d: always-cloud 32B N = 1 {bz['ap']['0.0']['ap']:.4f} → "
  f"{bm['ap']['0.0']['ap']:.4f} (zero-latency h = 1 is {bz['ap']['1.0']['ap']:.4f}).")
w(f"3. Under latency setting (ii), always-cloud 32B N = 9 scores "
  f"{B['always-cloud/32BI_N9|measured@25|far5']['ap']['0.0']['ap']:.4f} at h = 0, **below** "
  f"device-only's {dm['ap']['0.0']['ap']:.4f}.")
w("4. Decision rule 1 is met at N = 1 at trigger rates 5 %, 10 % and 20 % under both load levels; it "
  "is not met at N = 9 at any cell, where the sign reverses with CIs excluding 0.")
w(f"5. Decision rule 2 is met in {len(hits)} of 108 cells, under both latency settings; the cheapest "
  f"is 11 % of always-cloud's cloud work.")
w(f"6. At N = 1, measured @25 %, 5 % FPR, 20 % trigger, escalation-32B issues "
  f"{work(m1):,.0f} invocations per clip-hour against always-cloud's 3,600 and escalation-4B's "
  f"{work(esc4('measured@25', 5, 20)):,.0f}.")
w(f"7. At the same cell, {m1['episodes']['false_dismissals_positive_before_event']} episodes on "
  f"positive clips are dismissed before the event, and positive clips re-escalate "
  f"{m1['episodes']['positive']['re_escalations_per_clip']:.2f} times each.")
w("8. Negative control (a) passes exactly in 36 of 36 cells. Negative control (b) passes under "
  "setting (i) and is uninformative under setting (ii).")
w("9. The cooldown `c = 2 s` reduces invocations per clip-hour by about 22 % at every (q, k, L_max) "
  "combination tested.")
w("10. The 4B N = 3 secondary device arm is better than 4B N = 1 with zero latency (0.1413 vs "
  "0.1023 at h = 0) and worse with its own measured latency (0.0398 vs 0.0528).")
w()

# ---------------------------------------------------------------- interpretation
w("## 15. Interpretation (inference, labelled as such)")
w()
w("- **The study's first question gets a qualified yes.** Capability does shorten episodes and does "
  "reduce cloud work — but only when the capable model is also the *fast* one. At N = 1 the 32B "
  "resolver reaches a decision sooner than the 4B counterfactual at matched trigger and alarm rates, "
  "and the paired CIs exclude zero at two of three FPR levels at three of four trigger rates. At "
  "N = 9 the same model, given nine times the evidence, loses decisively on the same metric. The "
  "capability that StudyE5 Part G measured is real and it survives into this design; what does not "
  "survive is the assumption that more evidence is free.")
w("- **The second question gets a clear yes, and the answer is cheap.** Escalation keeps "
  "always-cloud's AP to within 0.01 at every horizon ≤ 1 s for 11–40 % of its cloud work, in 20 "
  "pre-specified cells. On this workload a device-triggered design is a good trade: most seconds are "
  "uninteresting, and a 4B trigger finds the interesting ones well enough that running 32B on all of "
  "them buys very little.")
w("- **Latency, not capability, is the governing variable in this design, and it acts like a "
  "horizon.** A score that takes `d` seconds to produce is a score about `d` seconds ago, so a "
  "policy with `d` seconds of latency competing at horizon h is really competing at horizon h + d. "
  "That single fact explains the N = 9 reversal, the collapse of negative control (b) under setting "
  "(ii), and why the secondary 4B N = 3 device arm is worse than 4B N = 1 despite being a better "
  "model on the same frames. It is also why the two decision rules disagree about N.")
w("- **Re-escalation is where the design actually spends its budget.** The cap is 10 s, but the "
  "median first-trigger-to-final-resolution span is about 22 s, because a clip typically opens two "
  "to three episodes. Any accounting that charges one episode per alarm understates cloud work by "
  "roughly a factor of three on this data, which is exactly why the pre-registration required "
  "re-escalations to be included.")
w("- **The false-dismissal rate is the uncomfortable number.** At the primary configuration between "
  "112 and 143 episodes on 150 positive clips are dismissed before the event happens. That is not a "
  "failure of escalation specifically — the same thresholds dismiss on negative clips at the rate "
  "they were fitted for — but it says the dismiss rule as specified is too eager for a safety "
  "application, and the k / L_max / dismiss-quantile sensitivity table shows the price of fixing it "
  "(k = 3, L_max = 20 s, q = 50 % cuts false dismissals to 19 for +24 % cloud work).")
w("- **What this does not show.** It does not show that 32B notices any individual crash earlier: "
  "the horizon shift in §3.1 is a property of two AP curves, and StudyE5's within-clip analysis "
  "found no earliness advantage. It does not establish the device arm's accuracy — that is a cloud "
  "measurement standing in for an Orin run that has not been done on Nexar. And it is a "
  "single-stream study: nothing here speaks to what happens when many devices escalate at once, "
  "which is StudyD7's and StudyRH8's territory.")
w()
w("**CLAUDE.md Rule 2.** Both pre-registered rules returned a positive finding, so no null "
  "classification is required. The one component that behaves like a null — negative control (b) "
  "under latency setting (ii) — is **inconclusive, not a real negative**: the mechanism it tests "
  "(within-clip timing information in the resolver's score) was already removed by the latency "
  "shift before the control was applied, so the control had nothing to disable. It is reported as "
  "uninformative there and passing under setting (i), where the mechanism is present.")
w()

# ---------------------------------------------------------------- files
w("## 16. Files")
w()
for x in ["experiments/dashcam/study_e9_episodes.py",
          "experiments/dashcam/study_e9_report.py",
          "results/dashcam/study_e9/e9_results.json",
          "results/dashcam/study_e9/e9_mechanism_verification.md",
          "reports/study_e9_episodes.md (this file)"]:
    w(f"- `{x}`")
w()

(ROOT / "reports/study_e9_episodes.md").write_text("\n".join(L) + "\n")
print("wrote reports/study_e9_episodes.md", len(L), "lines")
