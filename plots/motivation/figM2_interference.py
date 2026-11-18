"""M2 Interference.

Background requests' TTFT (y) against their arrival time in the trace (x) for one
paired run, without (grey) and with (colour) a cold 11k one-go rebuild injected
into the running server. The rebuild's engine span is shaded.

Source: StudyENG1d-loadedblock, the load level closest to P40 (P40 itself),
action mono11k. SELECTION RULE (fixed): the FIT pair whose total imposed delay
is the median of that cell's 15 FIT pairs.
  results/cost/study_eng1d/eng1d_trials_derived.jsonl  (per-trial imposed delay)
  results/cost/study_eng1d/eng1d_partC_requests_h100nvl.jsonl  (per-request rows)
Report reproduced: reports/study_eng1d_loadedblock.md section 7 (P40 mono11k total
imposed delay 44.87 s).
Caching: prefix caching ON; the 11k rebuild and the background requests carry
per-run uuid namespaces, so both arms are cold for the action and background KV
(0 cached-token mismatches between the paired arms).
"""
import json, statistics
import numpy as np
import matplotlib.pyplot as plt
import figstyle as F

F.apply_style()
ROOT = F.ROOT
LOAD, ACTION = "P40", "mono11k"

# ---- selection: the FIT pair whose imposed delay is the cell median --------
trials = [json.loads(l) for l in open(ROOT / "results/cost/study_eng1d/eng1d_trials_derived.jsonl")]
cell = [t for t in trials if t["load"] == LOAD and t["action"] == ACTION]
cell.sort(key=lambda t: t["total_imposed_s"])
cell_median = statistics.median([t["total_imposed_s"] for t in cell])
med_trial = cell[len(cell) // 2]          # odd n=15 -> the median pair itself
sel_trial = med_trial["trial"]
pair_imposed = med_trial["total_imposed_s"]
action_span = med_trial["action_span_s"]

# ---- the paired run's per-request rows -------------------------------------
rows = [json.loads(l) for l in open(ROOT / "results/cost/study_eng1d/eng1d_partC_requests_h100nvl.jsonl")]
sel = [r for r in rows if r.get("load") == LOAD and r.get("action") == ACTION and r.get("trial") == sel_trial]
inject = [r for r in sel if r["kind"] == "inject"][0]
inj_t = inject["t_inj_rel"]              # action's arrival offset within the 10 s trace
action_submit = inject["t_submit"]
# per-request arrival in trace seconds = t_submit - action_submit + inj_t.
# The two arms are separate runs; pair them by the background index (rid "...-bgN")
# so the without-arm point sits at the same arrival as its with-arm twin.
ep = [r for r in sel if r["kind"] == "episodic"]
with_ep = {r["rid"].split("-", 1)[1]: (r["t_submit"] - action_submit + inj_t, r["ttft_s"])
           for r in ep if r.get("mode") == "with" and r.get("rid")}
without_tt = {r["rid"].split("-", 1)[1]: r["ttft_s"] for r in ep if r.get("mode") == "without" and r.get("rid")}

fig, ax = plt.subplots(figsize=(F.COL1, 2.1))
# rebuild span shaded (engine span from the action's arrival)
ax.axvspan(inj_t, inj_t + action_span, color=F.C_COLD, alpha=0.12, lw=0)

cx = [a for a, _ in with_ep.values()]; cy = [t for _, t in with_ep.values()]
wx = [with_ep[k][0] for k in without_tt if k in with_ep]
wy = [without_tt[k] for k in without_tt if k in with_ep]
# label inside the shaded band at mid-height, clear of the legend and the
# top-right imposed-delay annotation
ax.text(inj_t + action_span / 2, max(cy) * 0.50, "cold 11k\nrebuild", ha="center",
        va="center", fontsize=6.2, color=F.C_COLD)
ax.scatter(wx, wy, s=10, color=F.C_WITHOUT, marker="o", edgecolor="none", alpha=0.85,
           label="without rebuild")
ax.scatter(cx, cy, s=12, color=F.C_WITH, marker="^", edgecolor="white", linewidth=0.3,
           label="with rebuild")
ax.set_xlabel("Arrival time in trace (s)")
ax.set_ylabel("Background request TTFT (s)")
ax.set_xlim(0, max(max(cx) + 0.3, inj_t + action_span + 1))
ax.set_ylim(0, max(cy) * 1.15)
ax.legend(loc="upper left", handlelength=1.0)
ax.annotate(f"imposed delay this pair {pair_imposed:.1f} s\n(cell median {cell_median:.1f} s)",
            (0.97, 0.80), xycoords="axes fraction", ha="right", fontsize=6.4, va="top")

pdf, png = F.save(fig, "figM2_interference")

payload = {
    "figure": "M2",
    "message": "A single cold 11k rebuild injected into a loaded server makes every request arriving during it wait seconds instead of milliseconds.",
    "selection_rule": "P40 mono11k FIT pair whose total imposed delay is the median of the cell's 15 FIT pairs",
    "selected_trial": sel_trial,
    "pair_imposed_delay_s": round(pair_imposed, 2),
    "cell_median_imposed_delay_s": round(cell_median, 2),
    "action_engine_span_s": round(action_span, 3),
    "inject_arrival_s": round(inj_t, 3),
    "n_background_with": len(with_ep), "n_background_without": len(without_tt),
    "source_file": "results/cost/study_eng1d/eng1d_trials_derived.jsonl, eng1d_partC_requests_h100nvl.jsonl",
    "report": "reports/study_eng1d_loadedblock.md section 7 (P40 mono11k 44.87 s)",
    "report_values": {"P40_mono11k_total_imposed_s": 44.87},
    "checks": {"pair_vs_report": F.ratio(pair_imposed, 44.87),
               "cell_median_vs_report": F.ratio(cell_median, 44.87)},
    "outputs": {"pdf": pdf, "png": png},
}
print(F.dump_json("figM2_interference", payload))
print("M2 done. trial", sel_trial, "imposed", round(pair_imposed, 2), "cell median", round(cell_median, 2),
      "span", round(action_span, 2), "inj_t", round(inj_t, 2))
