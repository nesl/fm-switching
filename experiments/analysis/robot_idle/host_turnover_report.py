#!/usr/bin/env python3
"""Render reports/study_host_turnover.md from host_turnover.json. Tables only, no plot."""
import json
from pathlib import Path
REPO = Path("/home/nesl/fm-switching")
J = json.load(open(REPO / "results/orchestration/live2/robot_idle/host_turnover.json"))
R = J["results"]
L = []
A = L.append
A("# Host-tier KV offload turnover per cell")
A("")
A("CPU only, read-only, no images. D240: 1x and kv0.5r reported separately, never pooled. "
  "Steady-state rate of vllm:kv_offload_store_bytes_total over the MIDDLE 60% of the run, at "
  "262,144 bytes/token; turnover = 110,592 / rate tokens.")
A("")
A('## The planner "337 tokens/s for BOTH rung-3 1x s4 and kv0.5r s4"')
A("")
r1 = R["1x"]["covex-v6-fair-final_s4"]
r0 = R["kv0.5r"]["covex-v6-fair-final_s4"]
A(f"Recomputed honestly over the middle 60%: 1x s4 = **{r1['rate_tokens_s']} tok/s** (turnover "
  f"{r1['turnover_s']} s), kv0.5r s4 = **{r0['rate_tokens_s']} tok/s** (turnover {r0['turnover_s']} "
  f"s). They are NOT identical (they differ by about 0.2 percent), so the planner's EXACTLY equal "
  f"337 for both was the artefact: a genuinely distinct pair cannot both be 337 to the digit. The "
  f"true rates are close because the host-offload store fills to about 1.05e11 bytes at both memory "
  f"levels over the run, but they are distinct cells with distinct slopes. Window: "
  f"{r1['n_window_samples']} samples each; store first/last 1x {r1['store_first_last_bytes']}, "
  f"kv0.5r {r0['store_first_last_bytes']}.")
A("")
for mem in ("1x", "kv0.5r"):
    A(f"## {mem}: per cell")
    A("")
    A("| arm | seed | agreement | rate tok/s | turnover s | n window | window dbytes |")
    A("|---|---|---|---|---|---|---|")
    for k in sorted(R[mem]):
        r = R[mem][k]
        A(f"| {r['arm']} | {r['seed']} | {r['agreement']} | {r['rate_tokens_s']} | "
          f"{r['turnover_s']} | {r['n_window_samples']} | {r['window_delta_bytes']} |")
    A("")
A("Full data: results/orchestration/live2/robot_idle/host_turnover.json")
(REPO / "reports/study_host_turnover.md").write_text("\n".join(L) + "\n")
print("wrote reports/study_host_turnover.md")
