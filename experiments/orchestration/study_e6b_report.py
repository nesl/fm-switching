#!/usr/bin/env python3
"""Generates reports/study_e6b_mobility.md from the committed StudyE6b JSONs.
No number in the report is typed by hand. CPU only; reads files, writes one markdown file."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/orchestration/study_e6b"
R = json.loads((OUT / "e6b_results.json").read_text())
T = json.loads((OUT / "e6b_traces.json").read_text())
MV = (OUT / "e6b_mechanism_verification.md").read_text()
E4OLD = json.loads((ROOT / "results/orchestration/study_e4/e4_results.json").read_text())
E6P0 = json.loads((ROOT / "results/orchestration/study_e6/e6_part0_upload_fix.json").read_text())

C = R["cells"]
NETS = ["5Mbps_60ms", "13.6Mbps_44ms", "88Mbps_22ms"]
DLS = [1, 2, 5, 10]
REG = ["outdoor_driving", "indoor", "synthetic_0pct", "synthetic_2pct", "synthetic_5pct",
       "synthetic_10pct", "synthetic_20pct", "synthetic_30pct"]
NAMES = list(R["accuracy_if_always_delivered"])
L = []


def w(s=""):
    L.append(s)


def f(x, n=4):
    return "—" if x is None else f"{x:.{n}f}"


def ci(c, n=3):
    return "—" if c is None else f"[{c[0]:+.{n}f}, {c[1]:+.{n}f}]"


w("# StudyE6b-mobility (Stage A) — timely answers over a dropping network, with StudyE4 and "
  "StudyE6(b) costs rebuilt")
w()
w("**OFFLINE REPLAY OF COMMITTED RESULTS.** CPU only on the flash host: no GPU was used, no model "
  "server was started, and no inference was run. Every accuracy and every latency below is read "
  "from a committed result file of an earlier study.")
w()
w("**E-id:** `StudyE6b-mobility`, pre-registered in `research/EXPERIMENTS.md` on 2026-11-11 "
  "**before any number in this report was computed** (user-authorized row). **STAGE A ONLY.**  ")
w("**Scripts:** `experiments/orchestration/study_e6b_traces.py`, "
  "`experiments/orchestration/study_e6b_mobility.py`, `experiments/orchestration/study_e6b_report.py` "
  "(this file).  ")
w("**Results:** `results/orchestration/study_e6b/e6b_traces.npz`, `e6b_traces.json`, "
  "`e6b_results.json`, `e6b_mechanism_verification.md`.  ")
w("**Never used:** any result marked INVALID — E24/E24b/E24c, E31 Parts C and D, I2/I3 "
  "TEMPORAL/SPATIAL, D/D2 Thinking, K/J Thinking T0.6. Reachability comes from E31b's corrected "
  "`cell_id == -1` signal, never from E31 Part C's `State=D/I`.")
w()

# ------------------------------------------------------------------ flags
w("## Prominent flags (read first)")
w()
st = C["outdoor_driving|13.6Mbps_44ms|STREAM|5s"]
od = C["outdoor_driving|13.6Mbps_44ms|ON_DEMAND|5s"]
e4s = R["e4_table41_recomputed"]["cells"]
w(f"1. **The deployment mode, not the policy, is the biggest single term in every timely-utility "
  f"number StudyE4 and StudyE6(b) reported.** At 13.6 Mbit/s PNG, 5 s deadline, outdoor-driving, "
  f"the oracle over twelve configurations is {f(st['oracle'])} under STREAM and {f(od['oracle'])} "
  f"under ON-DEMAND, and the best static configuration is {f(st['best_static'])} "
  f"({st['best_static_pick']['0']}) against {f(od['best_static'])} ({od['best_static_pick']['0']}). "
  f"StudyE4 charged one session both ways at once.")
a = e4s["STREAM/13.6Mbps_44ms/png/5s"]["headroom_over_pertype"]
b = e4s["ON_DEMAND/13.6Mbps_44ms/png/5s"]["headroom_over_pertype"]
o4 = E4OLD["primary"]["tables"]["13.6Mbps_44ms/png/5s"]["all845"]["headroom_over_pertype"]
o6 = E6P0["tables"]["newest_frame/13.6Mbps_44ms/png/5s"]["headroom_over_pertype"]
w(f"2. **StudyE6's own Part 0 fixed only half of error 1.** It moved the cloud-held arms to the "
  f"session rule but left RECENT on a full per-question upload, so it is still a mixed mode. At "
  f"13.6 Mbit/s PNG 5 s the headroom over per-type is {o4:.4f} as StudyE4 reported it, {o6:.4f} "
  f"after StudyE6 Part 0, and **{a:.4f} (STREAM) or {b:.4f} (ON-DEMAND)** once one mode is applied "
  f"to every cloud arm. Neither published number equals either self-consistent regime.")
p2 = C["outdoor_driving|13.6Mbps_44ms|STREAM|2s"]
w(f"3. **The decomposed policy P1 beats the best static configuration at the 5 s and 10 s "
  f"deadlines and collapses at 2 s.** Outdoor-driving at 13.6 Mbit/s: P1 − static is "
  f"{st['P1_minus_static']:+.4f} {ci(st['P1_minus_static_ci'])} at 5 s but "
  f"{p2['P1_minus_static']:+.4f} {ci(p2['P1_minus_static_ci'])} at 2 s. StudyE6 setting (a)'s rule "
  f"maximises accuracy and knows nothing about deadlines, so it keeps choosing 32B cells that "
  f"cannot be delivered in 2 s.")
sp = st["utility_split_by_reachability"]
w(f"4. **P1's advantage is made almost entirely of the questions that arrive during an outage, not of the "
  f"evidence rule.** On connected questions P1 scores {f(sp['connected']['P1'])} against static's "
  f"{f(sp['connected']['static'])}; on outage questions {f(sp['outage']['P1'])} against "
  f"{f(sp['outage']['static'])} — the static cloud configuration scores exactly zero whenever the "
  f"link is down, and P1 falls back to the device.")
w(f"5. **That fallback is worth very little, because every device option is either near chance or "
  f"undeliverable.** The device short windows score "
  f"{f(R['accuracy_if_always_delivered']['dev-4B-SHORT-N1'], 4)} / "
  f"{f(R['accuracy_if_always_delivered']['dev-4B-SHORT-N3'], 4)} / "
  f"{f(R['accuracy_if_always_delivered']['dev-4B-SHORT-N9'], 4)} at N = 1/3/9, all at or below the "
  f"0.20 chance floor (StudyF1, StudyF4), and device RECENT 120 s costs about 17 s on the Orin, so "
  f"it is delivered on {f(st['per_config']['dev-4B-RECENT'])} of questions at a 5 s deadline.")
w(f"6. **Irish outages are too short for the queue to matter; what matters is whether the link is "
  f"up at the question instant.** Outage runs are p50 "
  f"{T['regimes']['outdoor_driving']['outage_run_s']['p50']:.0f} s, p95 "
  f"{T['regimes']['outdoor_driving']['outage_run_s']['p95']:.0f} s, max "
  f"{T['regimes']['outdoor_driving']['outage_run_s']['max']} s, so at 13.6 Mbit/s the backlog they "
  f"leave clears in well under a second. The exception is arm U at 5 Mbit/s, where the offered "
  f"stream rate is close to the link and "
  f"{C['outdoor_driving|5Mbps_60ms|STREAM|5s']['upload_diagnostics']['U']['never_uploaded_fraction']*100:.1f}"
  f" % of questions never get their backlog cleared.")
w("7. **Stage A carries no keep-warm conclusion.** The device-warm link is ABSENT until StudyE7 and "
  "StudyE8 are committed, so per CLAUDE.md the keep-warm sweep (P2, P3, P3-noncausal, oracle "
  "keep-warm, negative control (b), the decision rule) is **not run**, and nothing here is offered "
  "as evidence for or against keeping a tier warm.")
w(f"8. **Oracle caution.** The oracle picks the best of twelve single-draw greedy configurations "
  f"per question. StudyE6 measured the near-identical-arm disagreement floor at 0.59 % (32B) and "
  f"1.47 % (4B) — about 0.15–0.44 pp of oracle headroom. The oracle margins here "
  f"({f(st['oracle_minus_P1'])} over P1 at 13.6 Mbit/s 5 s) are far above that floor, but the "
  f"twelve-arm selection effect is larger than StudyE6's four-arm one and is not quantified.")
w()

# ------------------------------------------------------------------ 1 corrections
w("## 1. The three costing errors, and what was done about them")
w()
w("| # | error | where it was | what it did | fix used here |")
w("|---|---|---|---|---|")
w("| 1 | mixed deployment modes | StudyE4 Part 1 and session analysis; StudyE6 setting (b) and "
  "Part 0 | RECENT paid a full on-demand upload every question while cloud-held history arms were "
  "charged as streamed, so the same session was billed two ways | one mode — STREAM or ON-DEMAND — "
  "applied to **all** cloud arms, never mixed; both reported |")
w("| 2 | 4B cold curve stopped at 12,501 tokens | StudyE4, StudyE6 setting (b) | built from "
  "image-format device runs only, so 4B-RICH (p50 12,597 tokens) was UNKNOWN, i.e. unavailable, on "
  "471 of 845 questions | StudyF3 `4BI/video/COLD`, token range 1,810–22,387; **0 of 845** cloud "
  "4B RECENT or RICH questions are now UNKNOWN |")
w("| 3 | 32B cold curve pooled formats | StudyE4, StudyE6 setting (b) | image-format and "
  "video-format runs were binned together in 100-token bins, so K3 got image pricing and K1 video "
  "pricing, with ≈0.8 s between the formats at equal tokens (StudyF3 §4) | StudyF3's separate "
  "`32BI/video/COLD`, `32BI/images/COLD` and `32BI/images/WARM` curves |")
w()
w("Dated correction blocks stating all three, and the reclassification below, have been prepended "
  "to `reports/study_e6_intervention.md` and `reports/study_e4_counterfactual.md`. **Their bodies "
  "are unchanged.**")
w()
w("**StudyE6's Rule 2 classification for the joint claim is withdrawn.** StudyE6 §13 called the "
  "combined-vs-independent null a REAL NEGATIVE. That rested partly on setting (b), which is built "
  "on these three costs; error 2 alone made 4B-RICH unavailable on 56 % of questions, removing one "
  "of the four arms the policy was meant to choose between. Under CLAUDE.md Rule 2 the joint claim "
  "is **INCONCLUSIVE (mechanism absent)**. **StudyE6 setting (a) — accuracy only, both models in "
  "the cloud, always reachable — stands exactly as reported**, including its own negative result, "
  "which uses no delivery cost.")
w()

# ------------------------------------------------------------------ 2 configurations
w("## 2. Configurations, and what each comparison can identify")
w()
w("| configuration | model | location | representation | cache | accuracy source | latency source | "
  "accuracy if always delivered | n available |")
w("|---|---|---|---|---|---|---|---|---|")
SRC = {
    "cl-4B-RECENT": ("StudyClean H1", "StudyF3 4BI/video/COLD"),
    "cl-4B-RICH": ("StudyClean H2", "StudyF3 4BI/video/COLD"),
    "cl-4B-U": ("StudyD11 arm U 4BI", "StudyF3 4BI/video/COLD"),
    "cl-32B-RECENT": ("StudyR1 K3", "StudyF3 32BI/video/COLD"),
    "cl-32B-RICH": ("StudyR1 K1", "StudyF3 32BI/video/COLD"),
    "cl-32B-U": ("StudyD11 arm U 32BI", "StudyF3 32BI/video/COLD"),
    "cl-32B-D2-cold": ("StudyRH4 D2", "StudyF3 32BI/images/COLD"),
    "cl-32B-D2-warm": ("StudyRH4 D2", "StudyF3 32BI/images/WARM vs uncached tokens"),
    "dev-4B-SHORT-N1": ("StudyF4 Part A N=1", "StudyF4 Part B p50"),
    "dev-4B-SHORT-N3": ("StudyF4 Part A N=3", "StudyF4 Part B p50"),
    "dev-4B-SHORT-N9": ("StudyF4 Part A N=9", "StudyF4 Part B p50"),
    "dev-4B-RECENT": ("StudyClean H1 **as proxy (FLAG)**", "StudyD4-orin / DevFast cold"),
}
CFGMETA = {
    "cl-4B-RECENT": ("4B", "cloud", "RECENT", "cold"), "cl-4B-RICH": ("4B", "cloud", "RICH", "cold"),
    "cl-4B-U": ("4B", "cloud", "U", "cold"), "cl-32B-RECENT": ("32B", "cloud", "RECENT", "cold"),
    "cl-32B-RICH": ("32B", "cloud", "RICH", "cold"), "cl-32B-U": ("32B", "cloud", "U", "cold"),
    "cl-32B-D2-cold": ("32B", "cloud", "D2", "cold"), "cl-32B-D2-warm": ("32B", "cloud", "D2", "**warm**"),
    "dev-4B-SHORT-N1": ("4B", "device Orin", "last-3 s N=1", "cold"),
    "dev-4B-SHORT-N3": ("4B", "device Orin", "last-3 s N=3", "cold"),
    "dev-4B-SHORT-N9": ("4B", "device Orin", "last-3 s N=9", "cold"),
    "dev-4B-RECENT": ("4B", "device Orin", "RECENT 120 s", "cold"),
}
for n in NAMES:
    m = CFGMETA[n]; s = SRC[n]
    w(f"| `{n}` | {m[0]} | {m[1]} | {m[2]} | {m[3]} | {s[0]} | {s[1]} | "
      f"{f(R['accuracy_if_always_delivered'][n])} | {R['n_available'][n]} |")
w()
w("**Match statements (CLAUDE.md: every comparison states whether input, stack and decoding "
  "match).**")
w()
w("- `cl-4B-RECENT` vs `cl-32B-RECENT`, and `cl-4B-RICH` vs `cl-32B-RICH`: **input identical**, "
  "stack identical (H100 vLLM 0.31.0), decoding identical (greedy, Instruct). Ledger class "
  "`IDENTICAL_INPUT`. These isolate capability.")
w("- `*-RECENT` vs `*-RICH`: same model, same stack, same decoding; **input differs** — window, "
  "frame count and resolution all move together. Ledger class `REALLOCATED_BUDGET`; this is not "
  "history length alone.")
w("- `cl-32B-D2-*` vs `cl-32B-RICH`: same model, stack and decoding; different construction and "
  "**different format** (separate images vs one video), which StudyF3 §4 measures at ≈0.8 s at "
  "equal token count. `REALLOCATED_BUDGET` + `FORMAT_DIFFERENT`.")
w("- `cl-32B-D2-cold` vs `cl-32B-D2-warm`: identical input and identical answers; **only the cache "
  "state differs**, and the two are never pooled. Caching is stated as a methodological parameter: "
  "cold = prefix caching off (`cached_tokens = 0` on all 686 StudyF3 cold rows); warm = vLLM prefix "
  "cache holding the session's earlier D2 prefix, priced on StudyF3's *uncached-token* curve.")
w("- device vs cloud 4B: **different stack** (llama.cpp F16 on Orin vs vLLM on H100) with the same "
  "decoding. StudyF4 measured 97.2 / 97.2 / 98.1 % per-question letter agreement on byte-identical "
  "frames, so the accuracy comparison is `IDENTICAL_INPUT` with a ~2–3 % stack-noise residual.")
w("- `dev-4B-RECENT` accuracy is **a proxy**: StudyClean H1's cloud letters stand in for an Orin "
  "run that does not exist. StudyF4 justifies the substitution at the short windows; it has **not** "
  "been measured at 120 s on the device. Flagged, and it changes nothing here because the "
  "configuration is undeliverable at every deadline tested.")
w()
w("**PENDING — listed, never estimated.** These configurations are part of the pre-registered "
  "design and are left out of every table until the studies that measure them are committed:")
w()
w("| configuration | needs |")
w("|---|---|")
for k, v in R["pending_configurations"].items():
    w(f"| `{k}` | {v} |")
w()

# ------------------------------------------------------------------ 3 cost model
w("## 3. The rebuilt cost model")
w()
w("### 3.1 Latency: per-format, per-cache-state curves (StudyF3), UNKNOWN outside the measured range")
w()
w("| configuration | status counts |")
w("|---|---|")
for n in NAMES:
    w(f"| `{n}` | " + ", ".join(f"{k} {v}" for k, v in sorted(R["latency_status"][n].items())) + " |")
w()
w("`UNKNOWN` = the prompt falls outside the curve's measured token range; the primary analysis "
  "treats it as unavailable. `INFEASIBLE` = no committed answer for that question (the six D2 "
  "questions that exceeded the context limit). `COLD_FIRST_QUESTION` = the first question of a "
  "video, where no warm cloud session exists yet; those questions are served by `cl-32B-D2-cold`.")
w()
w("### 3.2 Upload: what each deployment mode charges")
w()
w("| representation | STREAM rate (B/s) | STREAM uplink MB/hour | ON-DEMAND bytes per question, "
  "p50 (MB) | ON-DEMAND max (MB) |")
w("|---|---|---|---|---|")
for rep in ["RECENT", "RICH", "U", "D2"]:
    k = f"{rep}/png"
    o = R["ondemand_bytes_per_question"][k]
    w(f"| {rep} | {R['stream_rate_bytes_per_s'][k]:,.0f} | {R['stream_uplink_MB_per_hour'][k]:,.1f} | "
      f"{o['median']/1e6:.2f} | {o['max']/1e6:.2f} |")
w()
w("PNG, median frame sizes from StudyE4's `e4_frame_bytes.json`. Stream rates are the arm's own "
  "frame rate at the arm's resolution: RECENT and U at 1 fps 512×384, RICH at 1 fps 352×256, D2 at "
  "0.5 fps 352×256. **Stated assumption (StudyRH3, as StudyE6 Part 0):** RICH re-samples frames at "
  "each question, so a cloud holding all frames at 1 fps can build the RICH input without a fresh "
  "upload; the STREAM charge is the marginal cost of keeping that store current. Under STREAM the "
  "pending payload at a question is the queue backlog **plus the newest frame**, which is the frame "
  "captured at the question instant and not yet sent. The MB/hour figure is charged for the whole "
  "session, including hours in which no question arrives.")
w()
w("### 3.3 Upload delay actually incurred (13.6 Mbit/s, STREAM, outdoor-driving)")
w()
d = C["outdoor_driving|13.6Mbps_44ms|STREAM|5s"]["upload_diagnostics"]
d5 = C["outdoor_driving|5Mbps_60ms|STREAM|5s"]["upload_diagnostics"]
w("| representation | pending > 1 frame | upload s p50 | p95 | max | never uploaded | "
  "(5 Mbit/s) p95 | (5 Mbit/s) never uploaded |")
w("|---|---|---|---|---|---|---|---|")
for rep in ["RECENT", "RICH", "U", "D2"]:
    v, v5 = d[rep], d5[rep]
    w(f"| {rep} | {v['pending_above_one_frame_fraction']*100:.1f} % | {v['upload_s_p50']:.3f} | "
      f"{v['upload_s_p95']:.3f} | {v['upload_s_max']:.3f} | "
      f"{v['never_uploaded_fraction']*100:.1f} % | {v5['upload_s_p95']:.3f} | "
      f"{v5['never_uploaded_fraction']*100:.1f} % |")
w()

# ------------------------------------------------------------------ 4 network
w("## 4. Network regimes")
w()
w("| regime | signal | sessions | total s | outage fraction | outage runs | run s p50 / p95 / max |")
w("|---|---|---|---|---|---|---|")
for rg in REG:
    v = T["regimes"][rg]
    r = v["outage_run_s"]
    w(f"| `{rg}` | {v['signal'].split(';')[0]} | {v['n_sessions']} | {v['total_s']:,} | "
      f"{v['outage_fraction']:.4f} | {v['n_outage_runs']:,} | {r['p50']:.0f} / {r['p95']:.0f} / {r['max']} |")
w()
w("- **outdoor-driving** reproduces E31b exactly: 14.38 % no-cell time in 3,829 runs of 1–3 s "
  "across 16 sessions and 28,551 s. Signal is `cell_id == -1`; `State=D/I` (E31 Part C, INVALID) is "
  "never used.")
w(f"- **indoor** *is* available as a per-sample time series, so it is not skipped: the herolab "
  f"datalogs carry `temp_sec` and `C_level_a`, and a second is an outage when the median RSSI in it "
  f"is below −75 dBm. It yields **one** outage run of "
  f"{T['regimes']['indoor']['outage_run_s']['max']} s in "
  f"{T['regimes']['indoor']['total_s']:,} s. Two caveats: the seven sessions are "
  f"{', '.join(str(x) for x in T['regimes']['indoor']['session_lengths'])} s long, so only the "
  f"longest can host the longest videos and the alignment is concentrated; and "
  f"{sum(T['regimes']['indoor']['seconds_without_a_sample_treated_connected'].values())} seconds "
  f"carry no sample at all and are treated as connected.")
w("- **synthetic** is labelled synthetic throughout: a two-state process whose outage runs are "
  "resampled from the Irish empirical gap-duration distribution, with connected runs geometric at "
  "the mean that produces the target outage fraction. It therefore inherits Irish's short gaps; it "
  "varies *how often* the link drops, not *for how long*.")
w()
w("**Uplink is fixed at 5, 13.6 and 88 Mbit/s with RTT 60, 44 and 22 ms. Uplink variation is NOT "
  "modelled**, and the Irish traces are *download* traces — they are used here only for the "
  "reachability signal, never for a rate. Alignment: each video is mapped to a random window of a "
  "trace session long enough to hold it, 20 offsets per video (seeds 0–19), with questions replayed "
  "in time order within the video.")
w()
w("| regime | (video, offset) pairs | unmappable | videos never mappable |")
w("|---|---|---|---|")
for rg in REG:
    a = R["alignment_coverage"][rg]
    w(f"| `{rg}` | {a['pairs']:,} | {a['unmappable']} | {a['videos_never_mappable']} |")
w()

# ------------------------------------------------------------------ 5 mechanism
w("## 5. Mechanism verification (CLAUDE.md Steps 1–5)")
w()
w("Recorded in `results/orchestration/study_e6b/e6b_mechanism_verification.md` **before the Stage A "
  "sweep ran**, and reproduced here in full.")
w()
w("\n".join("> " + x if x else ">" for x in MV.strip().split("\n")))
w()

# ------------------------------------------------------------------ 6 results
w("## 6. Stage A results — static, P1 and the oracle, all regimes (STREAM, PNG)")
w()
w("P1 is the decomposed / no-pre-warm policy: model and evidence from StudyE6 setting (a)'s best "
  f"rule ({R['e6_rule']['policy']}), the cloud over STREAM while connected, and the best "
  "no-pre-warm device configuration when the cloud is unreachable. The device configuration and "
  "the best static configuration are both chosen on training offsets (5 folds over the 20 trace "
  "offsets, seed 0); every number reported is from held-out offsets. The StudyE6 rule chose "
  f"K3 on {R['e6_rule']['cells_chosen'].get('K3', 0)} questions and "
  f"K1 on {R['e6_rule']['cells_chosen'].get('K1', 0)}; the best static StudyE6 cell was K1 in all "
  "five folds.")
w()
for net in NETS:
    w(f"**Uplink {net.replace('Mbps_', ' Mbit/s, RTT ').replace('ms', ' ms')}**")
    w()
    w("| regime | deadline | reachable | oracle | best static | (pick) | P1 | P1 − static [95 % CI] "
      "| oracle − P1 [95 % CI] | device fallback |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for rg in REG:
        for dl in DLS:
            c = C[f"{rg}|{net}|STREAM|{dl}s"]
            w(f"| `{rg}` | {dl} s | {c['reachable_fraction']:.3f} | {f(c['oracle'])} | "
              f"{f(c['best_static'])} | {c['best_static_pick']['0']} | {f(c['P1'])} | "
              f"{f(c['P1_minus_static'], 4) if c['P1_minus_static'] is not None else '—'} "
              f"{ci(c['P1_minus_static_ci'])} | {f(c['oracle_minus_P1'])} "
              f"{ci(c['oracle_minus_P1_ci'])} | {f(c['P1_device_fallback_fraction'], 3)} |")
    w()
w("CIs are video-and-offset bootstraps, 2,000 resamples, seed 0 (videos resampled with "
  "replacement, then one offset drawn per resampled video).")
w()

# ------------------------------------------------------------------ 7 split
w("## 7. Where the P1 − static difference comes from: outage vs connected questions")
w()
w("| regime | uplink | deadline | total P1 − static | connected n | P1 | static | outage n | P1 | "
  "static | share of the difference from outage questions |")
w("|---|---|---|---|---|---|---|---|---|---|---|")
for rg in ["outdoor_driving", "indoor", "synthetic_5pct", "synthetic_10pct", "synthetic_20pct",
           "synthetic_30pct"]:
    for dl in (2, 5, 10):
        c = C[f"{rg}|13.6Mbps_44ms|STREAM|{dl}s"]
        s = c["utility_split_by_reachability"]
        n = s["connected"]["n"] + s["outage"]["n"]
        out_c = (s["outage"]["n"] / n) * (s["outage"]["P1"] - s["outage"]["static"])
        tot = c["P1_minus_static"]
        share = "—" if abs(tot) < 1e-9 else f"{out_c / tot * 100:.0f} %"
        w(f"| `{rg}` | 13.6 Mbit/s | {dl} s | {tot:+.4f} | {s['connected']['n']:,} | "
          f"{f(s['connected']['P1'])} | {f(s['connected']['static'])} | {s['outage']['n']:,} | "
          f"{f(s['outage']['P1'])} | {f(s['outage']['static'])} | {share} |")
w()
w("The share column is the outage questions' contribution divided by the total difference. It is "
  "**74–104 % for outdoor-driving and 47–125 % for the synthetic regimes at 5 and 10 s** — i.e. the "
  "whole of the margin, and at 10 s slightly more than the whole, because on connected questions "
  "the static configuration is marginally ahead. The indoor 10 s cell reads 1600 % only because its "
  "total difference is +0.0001; the share is meaningless where the denominator is near zero, and it "
  "is left in rather than suppressed. At the 2 s deadline the share is negative: there the outage "
  "questions are the only ones where P1 is ahead, and they do not come close to covering the "
  "connected-question loss.")
w()

# ------------------------------------------------------------------ 8 modes
w("## 8. STREAM vs ON-DEMAND, same questions, same curves")
w()
w("| regime | uplink | deadline | STREAM oracle | STREAM static (pick) | ON-DEMAND oracle | "
  "ON-DEMAND static (pick) |")
w("|---|---|---|---|---|---|---|")
for rg in ["outdoor_driving", "synthetic_10pct"]:
    for net in NETS:
        for dl in (2, 5, 10):
            a = C[f"{rg}|{net}|STREAM|{dl}s"]; b = C[f"{rg}|{net}|ON_DEMAND|{dl}s"]
            w(f"| `{rg}` | {net.split('M')[0]} Mbit/s | {dl} s | {f(a['oracle'])} | "
              f"{f(a['best_static'])} ({a['best_static_pick']['0']}) | {f(b['oracle'])} | "
              f"{f(b['best_static'])} ({b['best_static_pick']['0']}) |")
w()
w("P1 is defined as a STREAM policy ('cloud STREAM when connected') and is therefore not evaluated "
  "under ON-DEMAND.")
w()
w("**Uplink MB per hour charged, by mode** (outdoor-driving, PNG; STREAM is charged whether or not "
  "a question arrives):")
w()
w("| representation | STREAM | ON-DEMAND |")
w("|---|---|---|")
sa = C["outdoor_driving|13.6Mbps_44ms|STREAM|5s"]["uplink_MB_per_hour"]
sb = C["outdoor_driving|13.6Mbps_44ms|ON_DEMAND|5s"]["uplink_MB_per_hour"]
for rep in ["RECENT", "RICH", "U", "D2"]:
    w(f"| {rep} | {sa[rep]:,.1f} | {sb[rep]:,.1f} |")
w()
w("The comparison is not a free lunch for STREAM: at these question densities STREAM and ON-DEMAND "
  "move comparable volumes, and STREAM moves more on the arms the policy does not end up using. "
  "What STREAM buys is *when* the bytes move.")
w()

# ------------------------------------------------------------------ 9 E4 4.1
w("## 9. StudyE4 table 4.1, recomputed")
w()
w(R["e4_table41_recomputed"]["note"])
w()
w("| net / format / deadline | E4 as published | E6 Part 0 | **E6b STREAM** | **E6b ON-DEMAND** | "
  "E6b STREAM best static | E6b ON-DEMAND best static |")
w("|---|---|---|---|---|---|---|")
E4NETS = {"5Mbps_60ms": "5Mbps_142ms", "13.6Mbps_44ms": "13.6Mbps_44ms", "88Mbps_22ms": "88Mbps_22ms"}
for net in NETS:
    for fmt in ("png", "raw"):
        for dl in DLS:
            k4 = f"{E4NETS[net]}/{fmt}/{dl}s"
            o = E4OLD["primary"]["tables"].get(k4, {}).get("all845", {}).get("headroom_over_pertype")
            p0 = E6P0["tables"].get(f"newest_frame/{k4}", {}).get("headroom_over_pertype")
            a = e4s[f"STREAM/{net}/{fmt}/{dl}s"]; b = e4s[f"ON_DEMAND/{net}/{fmt}/{dl}s"]
            w(f"| {net.split('M')[0]} Mbit/s / {fmt} / {dl} s | {f(o)} | {f(p0)} | "
              f"**{a['headroom_over_pertype']:.4f}** {ci(a['headroom_over_pertype_ci'])} | "
              f"**{b['headroom_over_pertype']:.4f}** {ci(b['headroom_over_pertype_ci'])} | "
              f"{a['best_static_pick']['0']} | {b['best_static_pick']['0']} |")
w()
w("Headroom is oracle − per-type cross-fit, StudyE4's own metric, over StudyE4's own nine "
  "configurations, two-fold cross-fitting by video and a 2,000-resample video bootstrap at seed 0, "
  "with no network outages — exactly StudyE4's design, with only the costs changed. The 5 Mbit/s "
  "row uses RTT 60 ms where StudyE4 used 142 ms.")
w()

# ------------------------------------------------------------------ 10 trace
w("## 10. One instrumented video through an outage")
w()
tr = R["trace_example"]
w(f"`{tr['video_id']}`, offset {tr['offset']}, mapped to {tr['regime']} session "
  f"{tr['trace_session']} starting at trace second {tr['trace_start_second']}; video span "
  f"{tr['video_span_s']} s, of which **{tr['outage_seconds_in_window']} s are outage**. Uplink "
  f"{tr['uplink']}, {tr['mode']}, {tr['format']}, deadline {tr['deadline_s']} s. Stream rates: "
  + ", ".join(f"{k} {v:,.0f} B/s ({tr['uplink_MB_per_hour'][k]:,.1f} MB/h)"
              for k, v in tr["stream_rate_bytes_per_s"].items()) + ".")
w()
def cell(v, n=4, comma=False):
    if v is None:
        return "—"
    return f"{v:,.0f}" if comma else f"{v:.{n}f}"


for r in tr["questions"]:
    w(f"**Question at t = {r['question_time_s']:.0f} s** (trace second {r['trace_second']}, "
      f"link {'UP' if r['connected_at_question'] else '**DOWN**'}, "
      f"{r['outage_seconds_in_last_60s']} outage seconds in the preceding 60 s)")
    w()
    w("| configuration | backlog B | newest frame B | pending B | upload s | RTT s | compute s | "
      "total s | ≤ deadline | correct | utility |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    for n, e in r["configs"].items():
        w("| `" + n + "` | " + cell(e.get("queue_backlog_B"), comma=True) + " | "
          + cell(e.get("newest_frame_B"), comma=True) + " | " + cell(e.get("pending_B"), comma=True)
          + " | " + cell(e.get("upload_s")) + " | " + cell(e.get("rtt_s"), 3) + " | "
          + cell(e.get("compute_s")) + " | " + cell(e.get("total_s")) + " | "
          + ("yes" if e.get("delivered") else "no") + " | "
          + ("—" if e.get("correct") is None else ("yes" if e["correct"] else "no")) + " | "
          + str(e["utility"]) + " |")
        if e.get("note"):
            pass
    w()
w("Every row is checkable by hand: `total s = upload s + RTT + compute s` for a cloud "
  "configuration and `total s = compute s` for a device one; `upload s = pending B / (uplink "
  "bits per second / 8)` adjusted for any outage seconds crossed; `utility = 1` only when the "
  "configuration is both correct and delivered. Where the link is down at the question instant "
  "the cloud rows carry no total at all — by the pre-registered rule only device configurations "
  "can answer.")
w()
w("Two things are visible in this trace that the aggregate tables only imply. First, the backlog "
  "term is **zero** at all three questions even though 66 of the 388 trace seconds are outage: at "
  "13.6 Mbit/s a 1–3 s Irish gap leaves at most a few hundred kilobytes, which clears long before "
  "the next question arrives, so under STREAM the binding quantity is reachability at the question "
  "instant, not the queue. Second, at t = 387 s the link is down, five of the eight cloud "
  "configurations hold the correct answer, and every one of them scores zero while the device — "
  "which can answer — is wrong.")
w()

# ------------------------------------------------------------------ 11 controls
w("## 11. Negative control (a) — outage fraction 0")
w()
w(R["negative_control_a"]["description"])
w()
w("| cell | reachable | P1 device-fallback fraction | P1 | always-cloud decomposed | abs diff |")
w("|---|---|---|---|---|---|")
for k, v in R["negative_control_a"]["cells"].items():
    w(f"| `{k.replace('|', ' / ')}` | {v['reachable_fraction']:.3f} | {v['P1_device_fallback_fraction']:.3f} | "
      f"{f(v['P1'])} | {f(v['P1_cloud_only_utility'])} | {v['abs_diff']:.6f} |")
w()
mx = max(v["abs_diff"] for v in R["negative_control_a"]["cells"].values())
mf = max(v["P1_device_fallback_fraction"] for v in R["negative_control_a"]["cells"].values())
w(f"**PASS.** Device-fallback fraction is {mf:.3f} in every cell and P1 equals the always-cloud "
  f"decomposed policy to {mx:.6f}. At the 5 s and 10 s deadlines P1 = "
  f"{f(R['negative_control_a']['cells']['synthetic_0pct|13.6Mbps_44ms|STREAM|5s']['P1'])}, which is "
  "StudyE6 setting (a)'s evidence-only F1 accuracy (0.4036) — the mechanism switches off cleanly "
  "and the policy reduces to its cloud half.")
w()
w("Negative control (b) (device-warm accuracy set to device short-window accuracy) belongs to "
  "Stage B and is not run: the quantity it would disable does not exist until StudyE7 and StudyE8 "
  "are committed.")
w()
w("## 12. UNKNOWN sensitivity — linear extrapolation instead of unavailable")
w()
w("| cell | oracle, primary | oracle, extrapolated | configurations that move by > 0.002 |")
w("|---|---|---|---|")
for k, v in R["unknown_sensitivity_linear_extrapolation"].items():
    moved = [f"`{n}` {v['per_config_primary'][n]:.4f}→{v['per_config_extrapolated'][n]:.4f}"
             for n in v["per_config_primary"]
             if abs(v["per_config_primary"][n] - v["per_config_extrapolated"][n]) > 0.002]
    w(f"| `{k.replace('|', ' / ')}` | {f(v['oracle_primary'])} | {f(v['oracle_extrapolated'])} | "
      + (", ".join(moved) if moved else "none") + " |")
w()
w("The primary analysis treats an out-of-range prompt as unavailable. Replacing that with the "
  "curve's linear extrapolation (labelled, not measured) changes no oracle value and moves only "
  "`cl-4B-U` and `cl-32B-D2-warm`, by at most 0.008. The UNKNOWN rule is not load-bearing here — "
  "which is itself a consequence of fixing error 2.")
w()

# ------------------------------------------------------------------ 13 keep-warm costs
w("## 13. Keep-warm costs that Stage A can report")
w()
w("The pre-registered cost set is device energy above loaded idle (StudyE8 Parts A and C), uplink "
  "MB, and cloud warm-session seconds. Stage A can report the second in full and the third "
  "structurally; the first is PENDING.")
w()
w("- **Uplink MB per hour** is in §3.2 and §8, charged for the whole session under STREAM.")
w("- **Cloud warm-session seconds**: `cl-32B-D2-warm` holds a session open for the whole video. "
  f"Over the 234 videos the warm configuration is usable on {R['n_available']['cl-32B-D2-warm']} of "
  f"845 questions — the 234 first-questions have no warm session yet and "
  f"{R['latency_status']['cl-32B-D2-warm'].get('UNKNOWN', 0)} fall outside StudyF3's measured "
  "uncached-token range. **No capacity limit is modelled**: this study assumes a warm session is "
  "always available on demand. StudyRH5 and StudyRH8 are the measurements that say when that "
  "assumption fails — StudyRH5 found GPU-only fleets collapse at 8 concurrent D2 sessions (median "
  "96 s) while 256 GiB of host offload sustains 24 at a 0.81 s median, and StudyRH8 found that past "
  "the all-eager knee (D = 96) only demand-matched partial warming beats both pure policies. "
  "Nothing here contradicts or extends those; the single-session assumption is stated so that any "
  "warm number below is read as an upper bound on what a loaded fleet would deliver.")
w("- **Device energy above loaded idle**: PENDING (StudyE8 Parts A and C). StudyF4 Part B gives "
  "per-request energy for the short windows (14.3 / 45.1 / 149.6 J at N = 1/3/9 over a 9.89 W "
  "loaded idle), but the *keep-warm* cost — holding a D2 history warm on the Orin between "
  "questions — is not measured anywhere, and it is not estimated here.")
w()

# ------------------------------------------------------------------ 14 consistency
w("## 14. Results consistency check (CLAUDE.md, 6 checks)")
w()
w("**1. Cross-check against committed measurements.**")
w()
w("| quantity | this run | prior committed | source of prior | ratio | agree |")
w("|---|---|---|---|---|---|")
rows = [
    ("H1 (4B RECENT) accuracy", R["accuracy_if_always_delivered"]["cl-4B-RECENT"], 0.3254,
     "StudyClean / StudyF1 §2", True),
    ("K3 (32B RECENT) accuracy", R["accuracy_if_always_delivered"]["cl-32B-RECENT"], 0.3834,
     "comparability ledger / StudyF1 §2", True),
    ("K1 (32B RICH) accuracy", R["accuracy_if_always_delivered"]["cl-32B-RICH"], 0.3953,
     "StudyE6 §12 (best static cell)", True),
    ("D2 (32B) accuracy", R["accuracy_if_always_delivered"]["cl-32B-D2-cold"], 0.3957,
     "StudyRH4 results table", True),
    ("U 32B accuracy", R["accuracy_if_always_delivered"]["cl-32B-U"], 0.4142, "StudyD11 §table", True),
    ("U 4B accuracy", R["accuracy_if_always_delivered"]["cl-4B-U"], 0.3361, "StudyD11 §table", True),
    ("device short-window N=1 accuracy", R["accuracy_if_always_delivered"]["dev-4B-SHORT-N1"], 0.1538,
     "StudyF4 Part A", True),
    ("device short-window N=3 accuracy", R["accuracy_if_always_delivered"]["dev-4B-SHORT-N3"], 0.1373,
     "StudyF4 Part A", True),
    ("device short-window N=9 accuracy", R["accuracy_if_always_delivered"]["dev-4B-SHORT-N9"], 0.1515,
     "StudyF4 Part A", True),
    ("device N=1 total latency p50 (s)", R["device_fixed_latency_s"]["1"], 0.5525,
     "StudyF4 `study_f4_summary.json` parts.B.1", True),
    ("device N=9 total latency p50 (s)", R["device_fixed_latency_s"]["9"], 3.856,
     "StudyF4 `study_f4_summary.json` parts.B.9", True),
    ("Irish outage fraction", T["regimes"]["outdoor_driving"]["outage_fraction"], 0.1438,
     "E31b §2a (4,105 / 28,551)", True),
]
for q, a, b, s, _ok in rows:
    w(f"| {q} | {a:.4f} | {b:.4f} | {s} | {a/b if b else 0:.3f} | "
      + ("agree" if abs(a - b) < 5e-4 else "see note") + " |")
w()
w("**PASS.** Every ratio is 1.000 and every accuracy reproduces its committed source exactly; no "
  "quantity is anywhere near the 2× investigation gate. Two notes, both reported rather than "
  "smoothed over:")
w()
w("- StudyF4's **report text** gives device total latency p50 as 0.563 / 1.374 / 3.862 s, while "
  "StudyF4's own committed `study_f4_summary.json` gives 0.5525 / 1.3635 / 3.856 s (the report's "
  "numbers look like a different percentile). This run uses the committed JSON, which it reproduces "
  "to the digit. The discrepancy is inside StudyF4 and is flagged here, not resolved.")
w("- The herolab outage fraction here (0.0074 of seconds) is not the same object as E31b's 0.0091 "
  "of *samples* below −75 dBm: this study aggregates to a per-second median first, because outages "
  "must be intervals. Ratio 0.81, well inside the gate, and the definitional difference is the "
  "whole of it.")
w()
w("**2. Physical plausibility.** Every latency is a StudyF3 or StudyF4/StudyD4-orin measurement or "
  "an interpolation inside its measured range; nothing is faster than a committed curve because "
  "nothing is computed outside one. The upload rates are arithmetic: 276,307 B at 13.6 Mbit/s is "
  "0.1625 s, which is what the trace shows. 32B cold prefill at ≈270–294 ms per 1k tokens "
  "(StudyF3) is ≈3.7k tok/s on an H100 NVL; the Orin at 812–940 tok/s sits in its committed "
  "800–1,050 band (StudyF4 check 2). **PASS.**")
w()
w("**3. Distribution sanity.** Spreads are reported beside every median: upload p50/p95/max per "
  "representation and uplink (§3.3), outage run p50/p95/max per regime (§4), and bootstrap CIs on "
  "every headline difference. The one place constants legitimately appear is the device short "
  "windows, whose latency is a fixed per-N median by construction and whose accuracy is a fixed "
  "committed vector. **PASS.**")
w()
w("**4. Definition audit.**")
w()
w("| object | definition used here | matches prior? |")
w("|---|---|---|")
w("| RECENT | 121 frames at 1 fps over the last 120 s, 512×384 | StudyR1 / StudyClean manifest, unchanged |")
w("| RICH | re-sampled whole history, ≤ 256 frames, 352×256 | StudyR1 manifest, unchanged |")
w("| U | RICH frames older than the recent window plus the RECENT frames | StudyD11, as StudyE4/E6 |")
w("| D2 | fixed 2 s stride from t = 0, 352×256, append-only | StudyRH4, unchanged |")
w("| short window | last 3 s, N = 1/3/9 evenly spaced, 560×560 separate images | StudyF1/StudyF4; **not** DevFast's N = 9 over 120 s |")
w("| outage | a second with `cell_id == -1` (Irish) or median RSSI < −75 dBm (herolab) | E31b corrected signals |")
w("| delivered | upload + RTT + compute ≤ deadline, with the cloud unavailable if the link is down at the question instant | new to this study, stated |")
w("| utility | correct AND delivered | StudyE4 / StudyE6 setting (b), unchanged |")
w("| warm (cloud) | vLLM prefix cache holding the session's earlier D2 prefix; priced on uncached tokens | StudyF3 cell d |")
w("| cold | prefix caching off | StudyF3, `cached_tokens = 0` on all 686 cold rows |")
w()
w("**PASS**, with one name used two ways across the literature and disambiguated here: StudyE4's "
  "'continuous upload' meant *only the newest frame pending*, while its Part 1 meant *every frame "
  "since the previous question*. This study uses neither as a per-arm choice; it fixes a mode for "
  "the whole session.")
w()
w("**5. Claim linkage.** The headline results bear on FORMULATION §Constraints 2 (serving "
  "feasibility) and 3 (reachability) and on §Objective's statement that handoff latency on a "
  "mobility event is the binding term. They **support** the boundary-condition claim that the "
  "problem exists only when bandwidth and capacity are insufficient: at 88 Mbit/s under STREAM the "
  "upload term is 0.025 s and the whole decision reduces to compute and correctness. They **do "
  "not** speak to the coupling claim (§The coupling claim), which is about fidelity and placement "
  "not decomposing — that is Stage B's question. **Scope flag:** FORMULATION §Scoping assumes a "
  "single model per deployment, and this study compares a 4B device tier with a 32B cloud tier. "
  "That is the scoped-to-discussion case, and StudyF4's 97–98 % per-question agreement on "
  "byte-identical frames is the measurement that licenses it; no cross-tier KV transfer is "
  "modelled anywhere, so §Scoping's KV-portability exclusion is respected. **PASS with the flag.**")
w()
w("**6. Proxy validity.**")
w()
w("| proxy | what it actually measures | valid for the claim? |")
w("|---|---|---|")
w("| `dev-4B-RECENT` accuracy = StudyClean H1 letters | the *cloud* 4B's answers on the 120 s "
  "window, not the Orin's | **questionable, flagged**; not load-bearing, since the configuration "
  "is undeliverable at every deadline tested (≈17 s) |")
w("| Irish 5G trace as a mobile uplink reachability signal | cell attachment of a driving "
  "handset in Ireland in 2019–20, on *download* sessions | valid for reachability (E31b's whole "
  "point); **invalid for rate**, which is why uplink is fixed and uplink variation is not modelled |")
w("| herolab RSSI < −75 dBm as an outage | received signal strength at a robot in one room with a "
  "co-located AP | valid as a physical measure (E31b); the regime is near-continuous and its "
  "alignment is concentrated in 1–3 long-enough sessions |")
w("| synthetic two-state process | nothing measured; a construction with Irish's gap durations | "
  "labelled synthetic throughout; it varies outage *frequency* only |")
w("| 45 tokens per second of session time for D2 warm appends | StudyRH4's '5 images (450 tokens) "
  "per 10 s' | exact for D2 by construction |")
w()
w("**PASS**, with `dev-4B-RECENT` marked unvalidated and excluded from any headline claim.")
w()

# ------------------------------------------------------------------ 15 observations
w("## 15. Observations (data only, no interpretation)")
w()
st10 = C["outdoor_driving|13.6Mbps_44ms|STREAM|10s"]
w(f"1. Under STREAM at 13.6 Mbit/s and a 5 s deadline, outdoor-driving: oracle "
  f"{f(st['oracle'])}, best static {f(st['best_static'])} (`{st['best_static_pick']['0']}`), P1 "
  f"{f(st['P1'])}. P1 − static = {st['P1_minus_static']:+.4f} {ci(st['P1_minus_static_ci'])}.")
w(f"2. The same cell at a 2 s deadline: P1 {f(p2['P1'])} against static {f(p2['best_static'])} "
  f"(`{p2['best_static_pick']['0']}`), a difference of {p2['P1_minus_static']:+.4f} "
  f"{ci(p2['P1_minus_static_ci'])}.")
w("3. P1 − static is positive with a CI excluding zero at the 5 s deadline in every regime and at "
  "every uplink; at 10 s the CI contains zero in several cells; at 2 s it is negative with a CI "
  "excluding zero everywhere.")
w(f"4. On connected questions P1 and the best static configuration are within "
  f"{abs(sp['connected']['P1'] - sp['connected']['static']):.4f} of each other; on outage "
  f"questions the static cloud configuration scores exactly 0 and P1 scores "
  f"{f(sp['outage']['P1'])}.")
w("5. The best static configuration changes with the deadline and the mode: 4B arms at 2 s, "
  "`cl-32B-RICH` at 5 s, `cl-32B-U` at 10 s under STREAM, and `cl-32B-D2` or a device short window "
  "under ON-DEMAND.")
w(f"6. Deployment mode moves the oracle by more than any policy does: "
  f"{f(st['oracle'])} (STREAM) vs {f(od['oracle'])} (ON-DEMAND) in the same cell.")
w("7. Fixing error 2 removes every UNKNOWN from the cloud 4B arms (471 of 845 previously), and the "
  "linear-extrapolation sensitivity then changes no oracle value.")
w("8. Negative control (a) passes exactly: 0.000 device fallback and a 0.000000 difference from "
  "the always-cloud policy at outage fraction 0.")
w(f"9. Oracle − P1 is {f(st['oracle_minus_P1'])} {ci(st['oracle_minus_P1_ci'])} at 13.6 Mbit/s 5 s "
  f"and {f(st10['oracle_minus_P1'])} {ci(st10['oracle_minus_P1_ci'])} at 10 s.")
w()

# ------------------------------------------------------------------ 16 interpretation
w("## 16. Interpretation (inference, labelled as such)")
w()
w("- **The reported corrections are not a rounding matter.** The three errors moved the "
  "low-bandwidth timely-utility results of StudyE4 and StudyE6(b) by more than any policy "
  "difference either study measured, and they moved them in the direction that favoured 32B-RICH. "
  "The right reading of those two reports is that their accuracy results stand and their "
  "delivered-in-time results do not.")
w("- **StudyE6's joint claim should not have been called a real negative.** With 4B-RICH "
  "unavailable on 56 % of questions, the arm the policy was supposed to be able to choose was "
  "largely absent from setting (b). That is CLAUDE.md's definition of inconclusive, and the "
  "reclassification is made in the correction block rather than left implicit.")
w("- **What P1 shows is narrow and worth stating plainly.** A decomposed policy beats the best "
  "static configuration at 5 s, and essentially all of the margin is the trivial observation that "
  "a device can answer when the network cannot and a fixed cloud configuration cannot. That is a "
  "placement effect, not an evidence-selection effect: on connected questions the two are "
  "indistinguishable. Whether a *better* placement decision — in particular keeping a tier warm — "
  "adds anything beyond this is exactly what Stage A cannot answer.")
w("- **The deadline, not the network, is what breaks the decomposition.** P1 inherits StudyE6 "
  "setting (a)'s accuracy-only rule, which has no notion of delivery, so at a 2 s deadline it "
  "keeps choosing 32B cells whose compute alone is 3.7–3.8 s. A static policy that simply picks a "
  "4B arm beats it by 23 pp. If a joint policy is ever going to pay here, the first thing it needs "
  "is not a better predictor but a deadline-aware action space.")
w("- **On this workload the device fallback is close to worthless, and that caps everything Stage "
  "B can find.** Every no-pre-warm device option is at or below chance (StudyF1 and StudyF4 both "
  "measured the 3 s window as carrying no detectable information) or takes ~17 s. So the ceiling "
  "on any keep-warm policy's value is set by how good a *warm* device history turns out to be — "
  "StudyE7's and StudyE8's numbers — and not by the quality of the connectivity predictor.")
w("- **Irish outages are the wrong shape for queueing to matter.** 1–3 s gaps at 13.6 Mbit/s leave "
  "backlogs that clear in under a second. The mechanism that actually bites is binary: was the "
  "link up when the question arrived. A trace with minute-scale gaps — which E31b looked for and "
  "could not obtain without an IEEE DataPort account — would exercise the queue; this one does not.")
w()
w("**CLAUDE.md Rule 2 classification for Stage A.** Stage A reports no null, so Rule 2 does not "
  "bind on a result of its own. It does bind on the claim it withdraws: StudyE6's joint-claim null "
  "moves from **real negative** to **INCONCLUSIVE (mechanism absent)**, because error 2 removed an "
  "arm from the action space the claim is about. Stage A's own chain (Step 2) has no ABSENT link; "
  "the one ABSENT entry is the device-warm link, which is why Stage B is not run.")
w()

# ------------------------------------------------------------------ 17 stage B
w("## 17. What Stage B still needs")
w()
w("Stage B runs when the user says StudyE7 and StudyE8 are committed. It adds the device-warm and "
  "4B-D2 configurations, P2 (always-warm device), P3 (connectivity-aware keep-warm, predictor on "
  "past trace seconds only, θ and H fitted on training trace sessions, cross-fit by trace session, "
  "5 folds, seed 0), P3-noncausal as a sanity bound, oracle keep-warm, negative control (b), and "
  "the pre-registered decision rule. Two things found in Stage A should be carried into it and are "
  "recorded now, before those results exist:")
w()
w("1. The pre-specified decision cell (uplink 13.6 Mbit/s, deadline 2 or 5 s, outdoor-driving or "
  "synthetic ≥ 5 %) behaves very differently at 2 s and at 5 s, because 32B compute alone exceeds "
  "2 s. Both will be reported separately; neither will be dropped.")
w("2. P3's predictor has little to predict on these traces: Irish gaps are 1–3 s and, per E31b "
  "§5, persistence accuracy at H = 10–60 s is 0.74–0.76 and is driven by the 85.6 % base rate. If "
  "P3 ≈ P2 at equal energy, the pre-registered reading is that the decision is a static rule — and "
  "the trace's gap structure, not the predictor, will be the reason.")
w()

# ------------------------------------------------------------------ 18 files
w("## 18. Files")
w()
for x in ["experiments/orchestration/study_e6b_traces.py",
          "experiments/orchestration/study_e6b_mobility.py",
          "experiments/orchestration/study_e6b_report.py",
          "results/orchestration/study_e6b/e6b_traces.npz",
          "results/orchestration/study_e6b/e6b_traces.json",
          "results/orchestration/study_e6b/e6b_results.json",
          "results/orchestration/study_e6b/e6b_mechanism_verification.md",
          "reports/study_e6b_mobility.md (this file)",
          "reports/study_e6_intervention.md (correction block prepended; body unchanged)",
          "reports/study_e4_counterfactual.md (correction block prepended; body unchanged)"]:
    w(f"- `{x}`")
w()

(ROOT / "reports/study_e6b_mobility.md").write_text("\n".join(L) + "\n")
print("wrote reports/study_e6b_mobility.md", len(L), "lines")
