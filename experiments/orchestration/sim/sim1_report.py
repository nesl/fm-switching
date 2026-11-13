#!/usr/bin/env python3
"""Render reports/study_sim1_mixed.md from results/orchestration/sim1/. CPU only."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402

R = json.loads((ROOT / "results/orchestration/sim1/sim1_calibration.json").read_text())
DEST = ROOT / "reports/study_sim1_mixed.md"
L = []


def w(x=""):
    L.append(x)


def rr(x, n=2):
    if x is None:
        return "—"
    if isinstance(x, str):
        return x
    if x != x:
        return "—"
    if x == float("inf"):
        return "∞"
    return f"{x:.{n}f}"


w("# StudySIM1-mixed: the calibrated mixed-workload simulator — **THE CALIBRATION GATE FAILED, "
  "SO NO BASELINE WAS RUN**")
w()
w("E-id: StudySIM1-mixed (`research/EXPERIMENTS.md`, pre-registered 2026-11-12 before any "
  "computation). **Offline simulation over committed measurements. CPU only on the flash host: no "
  "GPU, no model server, no inference.** Baselines only: our scheduler is not in this study.")
w()
w("> ## STOP: the gate failed, and this report is the stop, not a result about baselines")
w(">")
w("> The pre-registered rule was: *the calibration gate must pass before any baseline run is "
  "interpreted; if it fails, stop and report which mechanism is missing, and do not tune free "
  "parameters to force a match.*")
w(">")
w(f"> **The gate FAILED.** Episodic p99 agrees within ±25 % in "
  f"**{R['p99_cells_agree']} of {R['p99_cells_total']} cells "
  f"({100 * R['p99_fraction_agree']:.0f} %, bar 80 %)** and the capacity level matches in "
  f"**{R['ladders_agree']} of {R['ladders_total']} ladders "
  f"({100 * R['ladders_fraction_agree']:.0f} %, bar 80 %)**.")
w(">")
w("> **The missing mechanism is named in §5 and it is not a parameter**: in the measured system a "
  "warm recall load raises the episodic **median** by 0.04–0.06 s, and in the simulator it raises "
  "it by nothing. The simulator therefore lacks the mechanism by which a resident long-context "
  "recall request lengthens *every* step it shares, not only the step that releases it. Every "
  "capacity disagreement is in a cell with warm sessions.")
w(">")
w("> **No baseline was run, no policy was compared and no sweep was started.** Under CLAUDE.md's "
  "Rule 1 a result from an uncalibrated simulator would be an artefact of the design, not "
  "evidence about any baseline, so there is nothing here to label INCONCLUSIVE — the experiment "
  "has not been performed.")
w()
w("## 1. Mechanism verification (CLAUDE.md Steps 1–5), recorded before any sweep")
w()
w("**Step 1 — the causal chain.** One 32B replica serves two workloads whose costs interact, and "
  "the chain the simulator must carry is measured end to end:")
w()
w("1. A recall request's reconstruction cost grows with its context (FORMULATION §refresh, "
  "§Objective): a cold 12.6k-token history costs about 3.8 s of frontend + encoder + LM prefill "
  "(StudyE10d), a host-warm 11k history 0.46 s and a GPU-warm one 0.38 s (StudyRH5 Part A).")
w("2. On a shared replica that cost becomes **queueing for the episodic stream**. vLLM 0.31.0's "
  "V1 scheduler serves RUNNING requests first and chunks prefills to a per-step token budget, so "
  "a long prefill takes the whole budget each step and an episodic request that arrives meanwhile "
  "is released only at the step that produces the long request's first token (StudyE10c §6: 99 % "
  "of slow episodic requests were submitted inside a cold recall's window and released a median "
  "0.00–0.24 s after its first token; StudyE10d localised the unit to the LM prefill; StudyE10e "
  "showed a per-step cap cuts the hold 19–30 % and does not remove it).")
w("3. A held episodic score is **delivered late**, and lateness has a measured price: StudyE9d's "
  "V(d) and d\\* (2.54 s on challenge mAP for 32B N = 1 at cadence 0.5 s, 1.13 s on streaming AP "
  "at h = 0).")
w("4. Where the warm state lives decides whether the recall side is cheap or catastrophic: past "
  "GPU KV (62,944 tokens) prefixes are evicted, and with GPU-only KV the next touch re-prefills "
  "the whole history (StudyRH5's collapse at D = 8; StudyE10b's at k = 8, median cached fraction "
  "0.002), while host offload turns the miss into a PCIe reload (StudyRH5 Part A).")
w("5. So a policy's choices of **representation** (how big the history is), **placement** (which "
  "tier holds it) and **timing** (when the work is admitted) jointly decide both the episodic "
  "quality and the recall timeliness, which is CLAIMS' joint claim and the thing the simulator "
  "exists to test baselines against.")
w()
w("**Step 2 — instantiate each link.** This is the table the gate exists to fill, and it is also "
  "where the gate failed. Values are from the calibration run (§3).")
w()
w("| causal link | implementing quantity | value / range in this run | varies as expected? | "
  "evidence |")
w("|---|---|---|---|---|")
_c0 = next(c for c in R["cells"] if c["condition"] == "C0" and c["n_frames"] == 1
           and c["level_pct"] == 40)
_c1 = next(c for c in R["cells"] if c["condition"] == "C1-r05" and c["n_frames"] == 1
           and c["level_pct"] == 10)
_k8 = next(c for c in R["cells"] if c["condition"] == "KVGPU-k8" and c["n_frames"] == 1)
_h8 = next(c for c in R["cells"] if c["condition"] == "KVHOST-k8" and c["n_frames"] == 1
           and c["level_pct"] == 25)
w(f"| episodic load → step time | episodic requests of 378 / 1,062 tokens at 5,708 tok/s | p99 "
  f"{rr(_c0['sim_p99_s'], 3)} s at the 40 % level against {rr(_c0['measured_p99_s'], 3)} s "
  f"measured; GPU utilisation {rr(100 * _c0['gpu_util'], 0)} % | **yes** | §3.1 |")
w(f"| cold recall → head-of-line hold | a 12,645-token prefill chunked at an 8,192-token budget | "
  f"episodic p99 {rr(_c1['sim_p99_s'], 2)} s against {rr(_c1['measured_p99_s'], 2)} s measured, "
  f"cold TTFT p50 {rr(_c1['cold_ttft_p50_s'], 2)} s against StudyE10e's 3.90 s | **yes** | §3.1, "
  "control (a) in §6 |")
w(f"| KV capacity → eviction → re-prefill | warm footprint ÷ 62,944 tokens, and the measured "
  f"warm-miss fraction | {_k8['re_prefills']} whole-history re-prefills at k = 8, "
  f"{_k8['evictions']} evictions; episodic p99 {rr(_k8['sim_p99_s'], 0)} s against "
  f"{rr(_k8['measured_p99_s'], 0)} s measured | **yes** | §3.1, control (b) in §6 |")
w(f"| host offload → reload instead of re-prefill | host reloads at StudyRH5's measured visible "
  f"cost | {_h8['host_reloads']} reloads and {_h8['re_prefills']} re-prefills at KV-HOST k = 8 | "
  "**yes** | §3.1 |")
w("| **warm residency → every step longer** | **ABSENT** | the measured episodic **p50** rises "
  "0.144 → 0.200 s under KV-HOST k = 8 and 0.146 → 0.211 s at C4; the simulator's p50 does not "
  "move at all (§3.3) | **NO — this link is ABSENT** | §3.3, §5 |")
w("| lateness → quality | StudyE9d's V(d), d\\* and blocking loss, read through "
  "`profiles.delay_curve` | the curves exist and are read by B10; **not exercised**, because no "
  "sweep ran | not tested | StudyE9d |")
w()
w("**Under CLAUDE.md Step 2 an ABSENT link is a stopping condition, and it fired.** The sweep was "
  "not run.")
w()
w("**Step 3 — trace one representative unit.** The engine is instrumented at step level and the "
  "calibration JSON carries per-cell counters (steps, step tokens, GPU busy seconds, evictions, "
  "re-prefills, host reloads, cap applications and cap exemptions). The per-unit trace that "
  "matters for the failure is the **p50 comparison** of §3.3: it is the instrument that located "
  "the absent link, and it is reported for every cell where a measured p50 exists.")
w()
w("**Step 4 — negative controls.** Three were pre-registered and all three behave as the "
  "mechanism predicts (§6): disabling the hold collapses the C1 tail, making KV unlimited removes "
  "the k = 8 collapse together with all its re-prefills, and making recall free returns every "
  "condition to C0 exactly. **So the mechanisms that ARE in the model do drive its results** — "
  "which is why the failure can be attributed to the one that is not.")
w()
w("**Step 5 — alternative explanations for the disagreement.** Three were considered and the data "
  "separate them:")
w()
w("| alternative | what it would predict | what the data show |")
w("|---|---|---|")
w("| the engine's SERVICE time is wrong | the episodic p50 would disagree everywhere | it agrees "
  "in every cell without warm sessions (ratios 0.94–1.03, §3.3) |")
w("| the disagreement is cell-to-cell NOISE, as StudyE10c says of its own ladders | "
  "disagreements in both directions, uncorrelated with the condition | true of the cold-only "
  "cells (0.62–1.80, both directions) but **not** of the warm cells, which are one-directional "
  "and systematic, and whose p50 disagreement cannot be noise |")
w("| one derived constant is mis-set | the warm cells would come into line at one end of its "
  "derivation range | they do not: no single value fits both k = 8 and k = 16 - at the upper "
  "derivation the k = 16 cells are still about 0.07 s below the measurement while the k = 8 cells "
  "already overshoot it, and the p50 gap closes at no value (§7) |")
w()
w("## 2. The engine model, and every constant with its source")
w()
w("One 32B vLLM 0.31.0 replica, discrete-event, deterministic per seed. The scheduler reproduces "
  "RUNNING-first service with chunked prefill at an 8,192-token step budget, vLLM's "
  "`long_prefill_token_threshold` cap **including its own \"only request\" exemption**, the vision "
  "encoder as one unsplittable step, GPU KV with eviction, and host offload.")
w()
w("| constant | value | source |")
w("|---|---|---|")
for k, v in E.SOURCES.items():
    val = getattr(E, k, None)
    if isinstance(val, float):
        val = f"{val:.6g}"
    elif isinstance(val, dict):
        val = ", ".join(f"{a}: {b}" for a, b in list(val.items())[:3]) + \
            (" …" if len(val) > 3 else "")
    elif val is None:
        val = "—"
    w(f"| `{k}` | {val} | {v} |")
w()
w("**Two constants are DERIVED rather than measured, and each of their two derivations "
  "disagrees.** Both are reported with their range and neither was changed to improve the gate:")
w()
w(f"- the **per-step overhead**: StudyE10e's P1 cold-TTFT ratio implies 0.016 s per step and its "
  f"P2 ratio implies 0.003 s. Registered value: the midpoint "
  f"{R['step_overhead_s']} s (range {R['step_overhead_range_s']}).")
w("- the **warm attention term** (engine time a warm request spends attending over its cached "
  "prefix): StudyE10b's utilisation delta at KV-HOST k = 8 implies 0.069 s per warm request and "
  "at k = 16 implies 0.142 s. Registered value: the midpoint 0.105 s at StudyE10b's mean history.")
w()
w("Sensitivity to both is reported in §7. **Nothing else in the model is free.**")
w()
w("## 3. The calibration gate")
w()
w(f"Rule, pre-registered: *{R['gate_rule']}*. Every cell runs StudyE10b / E10c's own workload — a "
  "30-s discard plus a 240-s window, Poisson episodic arrivals at a fraction of the measured peak "
  "(15.10 req/s at N = 1, 5.38 at N = 3), the condition's warm sessions appending every 10 s with "
  "one escalation in nine, and cold K1 recalls at r req/s — and reports the episodic p99 TTFT "
  "from the **scheduled** arrival, which is StudyD7 / E10b / E10c / E10e's definition.")
w()
w("The simulator reports the **median p99 over 5 arrival seeds** with the spread, where the "
  "measurements had one seed each. That is a reporting choice, not a parameter: StudyE10c itself "
  "records that its ladders are non-monotone from cell-to-cell noise at 350–1,800 requests per "
  "window, and the simulator can afford replication where the measurement could not.")
w()
w("### 3.1 Episodic p99 per cell")
w()
w("| condition | N | level | measured p99 | simulated p99 (median of 5) | min–max | ratio | "
  "agree? | measured source |")
w("|---|---|---|---|---|---|---|---|---|")
for c in R["cells"]:
    mm = (f"{rr(c.get('sim_p99_min'), 2)}–{rr(c.get('sim_p99_max'), 2)}"
          if c.get("sim_p99_min") is not None else "—")
    tag = ("**OK**" if c["agree"] else "**DISAGREE**")
    if c["agree"] and not c["within_25pct"] and c["collapse_agreement"]:
        tag = "**OK** (collapse)"
    w(f"| {c['condition']} | {c['n_frames']} | {c['level_pct']} % | "
      f"{rr(c['measured_p99_s'], 3)} s | {rr(c['sim_p99_s'], 3)} s | {mm} | "
      f"{rr(c['ratio'])} | {tag} | {c['source']} |")
w()
w(f"**{R['p99_cells_agree']} / {R['p99_cells_total']} agree "
  f"({100 * R['p99_fraction_agree']:.0f} %).** A collapse cell counts as agreeing when both "
  "numbers are more than 100x the budget: a ratio between two numbers that are each two orders of "
  "magnitude over the budget is not the quantity of interest, and that rule is stated here rather "
  "than applied silently.")
w()
w("### 3.2 Capacity per ladder")
w()
w("Capacity = the highest ladder level whose episodic p99 meets the budget (0.45 s at N = 1, "
  "1.21 s at N = 3), run bottom-up and stopped at the first failure, exactly as StudyE10c did. "
  "`—` means the lowest level already failed.")
w()
w("| condition | N | measured capacity | simulated capacity | agree? | simulated p99 by level | "
  "measured source |")
w("|---|---|---|---|---|---|---|")
for lad in R["ladders"]:
    by = ", ".join(f"{k} %: {rr(v, 2)}" for k, v in lad["sim_p99_by_level"].items())
    w(f"| {lad['condition']} | {lad['n_frames']} | "
      f"{(str(lad['measured_capacity_pct']) + ' %') if lad['measured_capacity_pct'] else '—'} | "
      f"{(str(lad['sim_capacity_pct']) + ' %') if lad['sim_capacity_pct'] else '—'} | "
      f"{'**OK**' if lad['agree'] else '**DISAGREE**'} | {by} | {lad['source']} |")
w()
w(f"**{R['ladders_agree']} / {R['ladders_total']} agree "
  f"({100 * R['ladders_fraction_agree']:.0f} %).** Every disagreement is a cell with WARM "
  "sessions, and in every one the simulator is **too optimistic**.")
w()
w("### 3.3 The p50 diagnosis — where the model actually breaks")
w()
w("A p99 disagreement can come from the service time or from the queueing. The episodic **p50** "
  "separates them, and it is the instrument that located the failure.")
w()
w("| condition | N | level | measured p50 | simulated p50 | ratio | reading |")
w("|---|---|---|---|---|---|---|")
for c in R["p50_cells"]:
    warm = c["condition"].startswith("KVHOST") or c["condition"] == "C4"
    read = ("**the median request pays and the simulator's does not**" if warm
            else "service time agrees")
    w(f"| {c['condition']} | {c['n_frames']} | {c['level_pct']} % | "
      f"{rr(c['measured_p50_s'], 3)} s | {rr(c['sim_p50_s'], 3)} s | {rr(c['ratio'])} | {read} |")
w()
w("**This is the finding of the report.** Without warm sessions the simulated service time is "
  "right to 2–6 %. With warm sessions the measured median episodic request is **0.04–0.06 s "
  "slower** (0.144 → 0.200 s at KV-HOST k = 8; 0.146 → 0.211 s at C4) while the simulated median "
  "does not move at all. A mechanism that slows the *median* request slows **more than half** of "
  "them, so it cannot be the head-of-line hold the simulator does model — that one slows only the "
  "requests that arrive inside a long prefill, which at these rates is a small minority.")
w()
w("## 4. Gate verdict")
w()
w("| criterion | bar | result | verdict |")
w("|---|---|---|---|")
w(f"| episodic p99 within ±25 % | ≥ 80 % of cells | {R['p99_cells_agree']} / "
  f"{R['p99_cells_total']} = {100 * R['p99_fraction_agree']:.0f} % | "
  f"**{'PASS' if R['gate_p99_pass'] else 'FAIL'}** |")
w(f"| capacity level matches | ≥ 80 % of ladders | {R['ladders_agree']} / "
  f"{R['ladders_total']} = {100 * R['ladders_fraction_agree']:.0f} % | "
  f"**{'PASS' if R['gate_capacity_pass'] else 'FAIL'}** |")
w(f"| **GATE** | both | — | **{R['GATE']}** |")
w()
w("Consequences, applied: **no baseline was run; no policy was compared; no sweep was started; "
  "no metric table exists in this report.** The pre-registered stop condition fired and the "
  "study stops here.")
w()
w("## 5. Which mechanism is missing")
w()
w("**The absent link: a resident long-context recall request lengthens every step it shares, for "
  "its whole residency — not only the step that releases the request it held.**")
w()
w("The evidence, in order:")
w()
w("1. **The measured median moves and the simulated median does not** (§3.3). Under KV-HOST "
  "k = 8 at 25 % load StudyE10b measured an episodic p50 of 0.200 s against 0.142 s with no "
  "recall load; the simulator gives 0.144 s in both. At C4 the measured p50 is 0.211 s and the "
  "simulator gives 0.146 s.")
w("2. **StudyE10b already named it, and this is the first time the project has had to model it:** "
  "\"the added p99 comes from episodic requests sharing steps with recall requests that attend "
  "over 8–10k-token contexts and wait on host loads. It is not a throughput limit: waiting max is "
  "2–11.\" A request that is *in the running batch* makes each step more expensive for everyone "
  "in it; the simulator charges a warm request's cost only to the steps that carry its own "
  "prefill, which is one step.")
w("3. **The quantity the simulator would need does not exist in the committed record.** Charging "
  "this correctly needs the per-step cost of a resident long-context request — a decode-phase "
  "(TPOT) interference measurement at 8–28k context on the 32B replica. StudyD7 / D7b, StudyRH5, "
  "StudyE10b / E10c / E10d / E10e all report **TTFT** and aggregate utilisation; none reports "
  "per-step or per-output-token cost under a mixed batch. The two derivations I could make from "
  "StudyE10b's utilisation deltas (0.069 s and 0.142 s of GPU per warm request) differ by 2x and "
  "**neither closes the gap** (§7), which is itself evidence that the missing quantity is not a "
  "scalar per request but a per-step cost that depends on how long the request stays resident.")
w("4. **It is one-directional and confined to warm cells.** All six capacity disagreements and "
  "five of the eleven p99 disagreements are warm cells, and in every one the simulator is too "
  "optimistic. The cold-only disagreements (C1 N1 at 10 %: 1.46; C4 N1 at 25 %: 0.62) go in both "
  "directions and are the size of the cell-to-cell noise StudyE10c documents in its own ladders.")
w()
w("**A second, smaller gap, stated separately:** at N = 3 the simulated p99 runs 1.21–1.27x the "
  "measurement at the low and middle levels while the p50 agrees to 6 %, so the queueing is "
  "slightly too strong there. It is inside the gate's ±25 % at 25 % load and outside it at 10 %. "
  "This is not the reason the gate failed and would not fix it.")
w()
w("## 6. Negative controls (Step 4)")
w()
w("Each disables one mechanism and checks the result collapses to the null. **All three pass**, "
  "which is what licenses the attribution in §5: the mechanisms that are in the model are the "
  "ones driving its numbers.")
w()
w("| control | what it disables | result | mechanism present? |")
w("|---|---|---|---|")
h = R["controls"]["hold_disabled"]
k = R["controls"]["kv_unlimited"]
f = R["controls"]["recall_free"]
w(f"| **(a) the hold** | caps a running prefill at ONE token per step, the strongest form of "
  f"\"the long prefill does not take the step\" | C1 episodic p99 {rr(h['c1_p99_s'], 3)} s → "
  f"{rr(h['c1_p99_hold_disabled_s'], 3)} s; C0 is {rr(h['c0_p99_s'], 3)} s | "
  f"**{'yes' if h['mechanism_present'] else 'NO'}** |")
w(f"| **(b) KV capacity** | GPU KV set to infinity | KV-GPU k = 8 p99 {rr(k['k8_p99_s'], 1)} s → "
  f"{rr(k['k8_p99_kv_unlimited_s'], 3)} s, and whole-history re-prefills "
  f"{k['k8_re_prefills']} → {k['k8_re_prefills_unlimited']} | "
  f"**{'yes' if k['mechanism_present'] else 'NO'}** |")
w(f"| **(c) recall cost** | all recall work free | C4 p99 {rr(f['c4_p99_s'], 1)} s → "
  f"{rr(f['c4_p99_recall_free_s'], 3)} s against C0's {rr(f['c0_p99_s'], 3)} s "
  f"(ratio {rr(f['ratio_to_c0'])}) | **{'yes' if f['mechanism_present'] else 'NO'}** |")
w()
w("Control (a) is worth one more line, because it did not do what a naive reading expects: "
  "capping at one token per step **raises** the C1 p99 "
  f"({rr(h['c1_p99_s'], 2)} → {rr(h['c1_p99_hold_disabled_s'], 2)} s) rather than lowering it to "
  "C0's. That is the correct behaviour and it reproduces StudyE10e's own finding from the other "
  "side: a one-token cap turns a 12,645-token prefill into 12,645 steps, each paying the per-step "
  "overhead, so the cold request takes far longer and the window during which it can hold "
  "anything is far wider. The control still does its job — it shows the *hold* is what the C1 "
  "tail is made of, because the tail tracks the prefill's duration and nothing else.")
w()
w("## 7. Sensitivity to the two derived constants")
w()
w("Neither constant was changed to improve the gate. Both ends of both derivations are run so a "
  "reader can see how much of the disagreement they could possibly explain.")
w()
w("**Per-step overhead** (derivations 0.003 s and 0.016 s; registered: the midpoint 0.010 s)")
w()
w("| overhead | C0 N = 1 at 40 % p99 | C1 N = 1 at 10 % p99 |")
w("|---|---|---|")
for ov, cell in R["step_overhead_sensitivity"]["cells"].items():
    w(f"| {ov} s | {rr(cell['c0_p99'], 3)} s | {rr(cell['c1_p99'], 3)} s |")
w(f"| *measured* | 0.383 s | 2.646 s |")
w()
w("**Warm attention term** (derivations 0.069 s and 0.142 s of GPU per warm request; registered: "
  "the midpoint 0.105 s)")
w()
ws = R["warm_attention_sensitivity"]
cols = list(ws["measured"].keys())
hdr = [c.replace("|", " / ") for c in cols]
w("| setting | " + " | ".join(hdr) + " |")
w("|---|" + "---|" * len(cols))
for lab, cells in ws["cells"].items():
    w(f"| {lab} | " + " | ".join(rr(cells[c], 3) for c in cols) + " |")
w("| **measured** | " + " | ".join(rr(ws["measured"][c], 3) for c in cols) + " |")
w()
w("**The constant cannot bring the four warm cells into line in either direction.** At the upper "
  "derivation two of them are still about 0.07 s SHORT of the measurement (KV-HOST k = 16 at 10 "
  "and 20 %: 0.364 and 0.405 against 0.440 and 0.478) while the other two OVERSHOOT it "
  "(KV-HOST k = 8: 0.420 against 0.339 at N = 1, 0.774 against 0.516 at N = 3) - the k = 8 cells "
  "are already too slow at the midpoint. No single value fits both k = 8 and k = 16, and **the "
  "p50 gap of §3.3 does not close at any value**, because this constant moves only the steps that "
  "carry a warm request's own prefill. That is the quantitative argument that the missing piece "
  "is a mechanism rather than a parameter: it needs a per-step cost that depends on how long a "
  "request stays resident, which is what §10 asks for.")
w()
w("## 8. What did NOT run, and what that does and does not mean")
w()
w("Not run: the workload builders, the metric computation and the baseline sweep (3 mixes x the "
  "fleet ladder x 3 deadlines x 20 seeds x every baseline arm, with the per-slice overhead swept "
  "over five values). The engine model and the calibration harness exist and are committed; the "
  "sweep does not.")
w()
w("**Classification, under CLAUDE.md Rule 2.** This is **neither a real negative nor an "
  "inconclusive result about any baseline** — it is a **design-stage stop before the sweep**, "
  "which is what the mechanism protocol is for. Step 2 found an ABSENT link and the pre-registered "
  "stopping condition fired. Nothing in this report bears on which baseline is better, and the "
  "`StudySIM1-mixed` row records the study as GATE FAILED rather than as a finding.")
w()
w("What **is** delivered and reusable: the engine model with every constant sourced "
  "(`sim/engine.py`), the calibration harness and its 29 cells, 16 ladders and 8 p50 cells "
  "(`sim/calibrate.py`), the three negative controls, the two sensitivity sweeps, and the "
  "diagnosis of §5 — which is a specific, falsifiable statement about what the next measurement "
  "has to measure.")
w()
w("## 9. Results consistency check (CLAUDE.md, 6 checks)")
w()
w("The numbers this report produces are the simulated cells. The protocol is run on them.")
w()
w("**1. Cross-check against committed measurements.** That is what the whole of §3 is: 29 p99 "
  "cells, 16 capacity ladders and 8 p50 cells, each against a named committed value. "
  f"{R['p99_cells_agree']} of {R['p99_cells_total']} p99 cells agree within ±25 %; the "
  "disagreements are tabulated with their ratios rather than smoothed, and the largest "
  "(C4 N = 1 at 10 %, 1.80x) is explained in §5. **No comparison is omitted and no value is "
  "chosen between two disagreeing sources**: where StudyE10b and StudyE10c measured the same cell "
  "with different ladders, both are quoted in the source column.")
w()
w("**2. Physical plausibility.** Every simulated rate is bounded by a committed one by "
  "construction: the episodic prefill rate is StudyD7b's measured peak (5,708 tok/s), the cold "
  "rates are StudyRH5's and StudyE10d's, and no simulated cell computes faster than its source. "
  f"Simulated GPU utilisation runs {rr(100 * min(c['gpu_util'] for c in R['cells']), 0)}–"
  f"{rr(100 * max(c['gpu_util'] for c in R['cells']), 0)} % against StudyE10b / E10c's measured "
  "20–100 %, and the simulated computed-tok/s never exceeds the 5.7k ceiling except in the "
  "collapse cells, where the measurement does the same.")
w()
w("**3. Distribution sanity.** Each cell is run over 5 arrival seeds and the median p99 is "
  "reported **with its min and max**, because a p99 over 350–1,800 requests is a 3-to-18-request "
  "statistic. The spread is large in exactly the places it should be — the cold-recall cells, "
  "where a p99 depends on whether a cold arrival landed next to an episodic one. No constant "
  "appears where a distribution is expected, except the simulated episodic p50 (0.144 s in every "
  "no-warm cell), **and that constant is the finding of §3.3, not a short-circuit**.")
w()
w("**4. Definition audit.**")
w()
w("| object | this run | prior committed definition | match |")
w("|---|---|---|---|")
w("| episodic p99 | TTFT from the SCHEDULED arrival, linear interpolation; unfinished requests "
  "count as infinite with a nearest-rank p99 | StudyD7 / E10b / E10c / E10e | **yes** |")
w("| capacity | highest ladder level meeting the budget, bottom-up, stop at the first failure | "
  "StudyE10c | **yes**, and at StudyE10c's ladder resolution |")
w("| budget | 0.45 s (N = 1) / 1.21 s (N = 3) | StudyE10b / E10c / E10e | **yes** |")
w("| level | fraction of the measured peak, 15.10 req/s (N = 1) / 5.38 (N = 3) | StudyD7b / D7 | "
  "**yes** |")
w("| window | 30-s discard + 240-s measured + 300-s drain cap | StudyE10b / E10c | **yes** |")
w("| warm session | a D2 history growing at 45 tokens per second of session time to StudyRH5's "
  "11k size, appending every 10 s with one escalation in nine | StudyRH4 / RH7 / E10b | **yes**, "
  "and the growth is why GPU KV crosses 1x between k = 4 and k = 8 as StudyE10b measured |")
w("| warm miss | a lookup from StudyE10b's measured miss fractions by warm footprint (0 below "
  "1x, 0.81 at about 1.2x, 0.91 at about 2.4x), each miss a whole-history re-prefill | StudyE10b "
  "/ RH5 | **a RULE from those measurements**, declared as such |")
w("| \"p99 of a cell\" | the **median over 5 arrival seeds**, with min and max | one seed per cell "
  "| **DIFFERENT, deliberately and declared** (§3) |")
w()
w("**5. Claim linkage.**")
w()
w("| result | claim it bears on | supports / weakens / silent |")
w("|---|---|---|")
w("| the engine model reproduces the cold-recall hold and the KV-GPU collapse, within noise | "
  "FORMULATION §refresh, and StudyE10b / E10c / E10d / E10e's own conclusions | **supports** "
  "them: the hold and the eviction chain are reproducible from the measured constants alone |")
w("| a resident long-context recall request slows the MEDIAN episodic request, and that mechanism "
  "is not in any of our models | CLAIMS' joint claim (representation x placement x timing) | "
  "**neither supports nor weakens it** — it says the instrument is not yet able to test it |")
w("| no baseline comparison | CLAIMS' joint claim | **silent**, by the stop |")
w()
w("**6. Proxy validity.**")
w()
w("| proxy | what it actually measures | valid? |")
w("|---|---|---|")
w("| the simulator stands for one 32B replica | a step-level model calibrated to StudyE10b / "
  "E10c / E10e | **NOT YET** — that is the gate's verdict, and §5 says what is missing |")
w("| a D2 history growing at 45 tok/s stands for StudyE10b's StudyRH2-planned sessions | a "
  "staggered linear growth to 11k tokens | **reasonable and declared**: it reproduces the warm "
  "footprint crossing 1x KV between k = 4 and k = 8, which is the behaviour E10b measured, but "
  "the individual session sizes are not E10b's |")
w("| the warm-miss lookup stands for vLLM's block-level prefix eviction | a footprint-to-miss "
  "fraction from StudyE10b's own counts | **declared as a rule**; it reproduces the collapse and "
  "its absence at k = 4, and it is the reason the KV-GPU cells agree |")
w()
w("**Consistency check: PASS 6 / 6** on the numbers produced, with the one declared definitional "
  "difference (the 5-seed median) and the ABSENT link reported rather than hidden.")
w()
w("## 10. What is needed to pass the gate")
w()
w("Two things, and the first is a measurement the project does not have:")
w()
w("1. **A per-step interference measurement for a resident long-context request** on the 32B "
  "replica: how much longer a scheduler step takes when it carries a request attending over "
  "8–28k cached tokens, and for how many steps that request stays resident. StudyE10b's "
  "utilisation deltas bound it only to within 2x and, as §7 shows, no value in that range closes "
  "the p50 gap. The natural shape is a short study on the same harness: one 32B replica, a fixed "
  "episodic load, k warm sessions, and the **episodic p50 and TPOT** recorded per cell rather "
  "than the TTFT p99 alone — StudyE10b's own rows may already contain enough to extract it, which "
  "is a question about its committed per-request data, not a new GPU run.")
w("2. **A decision about the gate's scope.** The gate as written mixes cells whose mechanism the "
  "model reproduces (C0, C1, KV-GPU: 13 of 13 within ±25 % or collapse-agreeing) with cells whose "
  "mechanism it does not (the warm KV-HOST cells). An alternative is to pass the gate on the "
  "mechanisms the simulator does carry, run the sweep **with warm-recall arms excluded and that "
  "exclusion declared**, and add the warm arms once (1) exists. That is a scoping decision with "
  "real consequences for what the sweep can claim, so it is not mine to take.")
w()
w("## 11. Files")
w()
w("| file | what |")
w("|---|---|")
w("| `experiments/orchestration/sim/engine.py` | the engine model: the step scheduler, the cap "
  "and its exemption, KV residency and eviction, and every constant with its source |")
w("| `experiments/orchestration/sim/calibrate.py` | the calibration harness: 29 p99 cells, 16 "
  "capacity ladders, 8 p50 cells, 3 negative controls, 2 sensitivity sweeps |")
w("| `experiments/orchestration/sim/sim1_report.py` | this report |")
w("| `results/orchestration/sim1/sim1_calibration.json` | every cell, counter, control and "
  "sensitivity value |")
w("| `reports/study_sim1_mixed.md` | this file |")
w()
w("Inputs, all committed: StudyD7 / D7b capacity and peaks, StudyRH5 Part A and fleet, StudyRH4 "
  "D2 sizes, StudyRH7 / RH8 append cadence, StudyE10b / E10c / E10d / E10e cells, and StudyE9d's "
  "delay curves (read by the policies, not yet exercised). Run on flash, **CPU only** — no GPU, "
  "no model server, no inference.")
w()

txt = "\n".join(L)
bad = []
for i, ln in enumerate(txt.split("\n")):
    if ln.startswith("|---"):
        n = ln.count("|")
        if txt.split("\n")[i - 1].count("|") != n:
            bad.append(i + 1)
DEST.write_text(txt)
print("wrote", DEST, "lines", len(txt.split("\n")),
      "tables", sum(1 for ln in txt.split("\n") if ln.startswith("|---")), "malformed", bad)
