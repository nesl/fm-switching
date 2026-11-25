#!/usr/bin/env python3
"""Render reports/study_d242_correlated_outage.md from d242_correlated_outage.json. No plots."""
import json
from pathlib import Path
REPO = Path("/home/nesl/fm-switching")
J = json.load(open(REPO / "results/orchestration/live2/robot_idle/d242_correlated_outage.json"))
R = J["results"]; m = J["model"]
L = []; A = L.append
A("# D242 correlated multi-robot outage screen (rung-3 1x)")
A("")
A("**MODEL-BASED SCREEN, NOT A MEASUREMENT.** First-token times are predicted by the committed D162 "
  "model; the engine is not run. 1x only. k robots lose the link together; at reconnect their "
  "catch-up (reload if the history does not fit the pool, plus backlog) is served in order.")
A("")
A(f"- D162: {m['d162']}; deadline {m['deadline_s']} s; GPU pool {m['gpu_pool_tokens']} tokens minus "
  f"the non-robot working set ({m['non_robot_working_set']}).")
A(f"- backlog = {m['backlog']}; context limit {m['context_limit']}.")
A(f"- reload: {m['reload_assumption']}.")
A(f"- queued_ahead = {m['queued_ahead']}.")
A("- Orderings: (a) FIFO by reconnect; (b) earliest next question (ORACLE bound); (c) largest "
  "deficit first; (d) all histories evicted (baseline).")
A("")
A("## Headline")
A("")
A("Recovery ORDER adds almost nothing: the (b) oracle ordering beats (a) FIFO by at most 0.006 "
  "across every k and D, because all k robots reconnect at the same instant and the binding "
  "constraint is the TOTAL catch-up work (queued-ahead accumulates regardless of order), not who "
  "goes first. The real lever is keeping histories warm versus evicting them: (a)-(c) run far above "
  "(d) at every k and D. P(first token within 3 s) falls steeply as k and D grow (more robots "
  "sharing the pool, bigger backlog), and the context limit is exceeded only at D=180 s (~2-3 "
  "percent of robot-windows). The counterfactual-ordering room is the (b) minus (a) gap below; it "
  "is essentially zero.")
A("")
A("## P(first token within 3 s) by k and outage D, pooled over rung-3 1x seeds 4 to 7")
A("")
A("| k | D (s) | (a) FIFO | (b) earliest-next (oracle) | (c) largest-deficit | (d) all-evicted | (b)-(a) gap | ctx exceeded | mean device-only Q in window | n robot-windows |")
A("|---|---|---|---|---|---|---|---|---|---|")
for k in (1, 3, 5, 7):
    for D in (60, 120, 180):
        r = R[f"k{k}_D{D}"]
        A(f"| {k} | {D} | {r['a_fifo']} | {r['b_earliest_next_oracle']} | {r['c_largest_deficit']} "
          f"| {r['d_all_evicted']} | {r['b_minus_a_gap']} | {r['frac_ctx_exceeded']} | "
          f"{r['mean_device_only_questions_in_window']} | {r['n_robot_windows']} |")
A("")
A("Full data: results/orchestration/live2/robot_idle/d242_correlated_outage.json")
(REPO / "reports/study_d242_correlated_outage.md").write_text("\n".join(L) + "\n")
print("wrote reports/study_d242_correlated_outage.md")
