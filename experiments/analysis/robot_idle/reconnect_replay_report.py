#!/usr/bin/env python3
"""Render reports/study_reconnect_replay.md from reconnect_replay.json. Tables only, no plot."""
import json
from pathlib import Path
REPO = Path("/home/nesl/fm-switching")
J = json.load(open(REPO / "results/orchestration/live2/robot_idle/reconnect_replay.json"))
R = J["results"]
POL = [("i_hist_kept_catchup_question", "(i) history kept, catch up at question"),
       ("ii_hist_kept_catchup_reconnect", "(ii) history kept, catch up at reconnect"),
       ("iii_hist_evicted", "(iii) history evicted")]
L = []
A = L.append
A("# Reconnect cost-model replay (rung-3 1x, robot questions)")
A("")
A("**MODEL-BASED SCREEN, NOT A MEASUREMENT.** First-token time is PREDICTED by the committed D162 "
  "model; the engine is not run. This is a NETWORK experiment and is **1x only** (D240: kept "
  "separate from the memory experiments, never pooled with them).")
A("")
m = J["model"]
A(f"- D162: {m['d162']}; deadline {m['deadline_s']} s.")
A(f"- backlog = {m['backlog']}, frame stride {m['frame_stride_s']} s; tokens/frame measured per "
  f"seed = {J['tokens_per_frame_by_seed']} (the D2 ~90 law, confirmed).")
A(f"- queued_ahead is each question's own measured in-flight uncached tokens at its submit.")
A("- Policies: " + "; ".join(v for _, v in POL) + ".")
A("")
A("## Headline")
A("")
A("Keeping the history and catching up the backlog AT RECONNECT (policy ii) holds P(first token "
  "within 3 s) at about 0.99 regardless of outage length, because the backlog is warm by the time "
  "the question arrives. Catching up AT QUESTION time (policy i) degrades as the outage grows (the "
  "whole backlog must prefill at the question). Evicting the history (policy iii) is catastrophic "
  "even at 60 s. The gap between (ii) and (i)/(iii) is the room an outage-aware recovery policy "
  "has: keep the history resident and pre-warm the backlog before the next question.")
A("")
A("## P(first token within 3 s), pooled over rung-3 1x seeds 4 to 7")
A("")
pooled = R["pooled_1x"]
A(f"n_questions = {pooled['n_questions']}; tokens/frame median = {pooled['tokens_per_frame_median']}.")
A("")
A("| outage D | (i) catch-up at question | (ii) catch-up at reconnect | (iii) evicted |")
A("|---|---|---|---|")
for D in ("D60", "D120", "D300"):
    p = pooled["p_within_3s"][D]
    A(f"| {D[1:]} s | {p['i_hist_kept_catchup_question']} | "
      f"{p['ii_hist_kept_catchup_reconnect']} | {p['iii_hist_evicted']} |")
A("")
A("## Per seed")
A("")
A("| seed | n questions | tok/frame | D | (i) | (ii) | (iii) |")
A("|---|---|---|---|---|---|---|")
for seed in sorted(R["per_seed"]):
    s = R["per_seed"][seed]
    for D in ("D60", "D120", "D300"):
        p = s["p_within_3s"][D]
        A(f"| {seed} | {s['n_questions']} | {s['tokens_per_frame']} | {D[1:]} s | "
          f"{p['i_hist_kept_catchup_question']} | {p['ii_hist_kept_catchup_reconnect']} | "
          f"{p['iii_hist_evicted']} |")
A("")
A("Full data: results/orchestration/live2/robot_idle/reconnect_replay.json")
(REPO / "reports/study_reconnect_replay.md").write_text("\n".join(L) + "\n")
print("wrote reports/study_reconnect_replay.md")
