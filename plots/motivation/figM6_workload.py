"""M6 Real workload.

CDF of the robot's history size in tokens at each question's real time on the
S-EMBER D2 append-only history (sessions played from the start). The history
size is the request's prompt-token count under the D2 representation. Two
reference lines at 11k and 28k carry the committed cold-rebuild time at those
sizes, so a reader can read a history length off the x-axis and the cost of
rebuilding it off the annotation.

Sources (read-only):
  results/sember/study_e7/e7_requests_h100nvl.jsonl  (StudyE7 Job A, D2, 4B)
  cold-rebuild anchors: results/cost/study_eng1f/eng1f_results.json Part 1
    (cold recompute 11k = 2.69 s, 28k = 7.57 s), cross-checked against
    StudyENG1 Part B monolithic 11k = 2.755 s.
Reports: reports/study_e7_d2_4b.md section 1 (prompt tokens 511-30,701, p50
10,584), reports/study_eng1f_disk.md section 5, reports/study_eng1_steptime.md.
Caching: the token counts are input sizes (no latency); the cold-rebuild anchors
are prefix-caching-off cold recompute measurements on the 32B serving stack.
"""
import json, statistics
import numpy as np
import matplotlib.pyplot as plt
import figstyle as F

F.apply_style()

rows = [json.loads(l) for l in open(F.ROOT / "results/sember/study_e7/e7_requests_h100nvl.jsonl")]
d2 = [r for r in rows if not r.get("grey") and not r.get("infeasible") and r.get("prompt_tokens")]
tok = np.array(sorted(r["prompt_tokens"] for r in d2), dtype=float)
n = len(tok)
med = int(statistics.median(tok))
cdf = np.arange(1, n + 1) / n

# cold-rebuild anchors (committed)
eng1f = json.load(open(F.ROOT / "results/cost/study_eng1f/eng1f_results.json"))
cold_11k = eng1f["part1"]["11k|cold"]["ttft_s"]["median"]   # 2.6866
cold_28k = eng1f["part1"]["28k|cold"]["ttft_s"]["median"]   # 7.5716

fig, ax = plt.subplots(figsize=(F.COL1, 2.1))
ax.plot(tok, cdf, color=F.C_WORKLOAD, lw=1.3)
ax.set_xlabel("History size at question time (tokens)")
ax.set_ylabel("CDF over questions")
ax.set_xlim(0, 31000)
ax.set_ylim(0, 1.0)
ax.grid(True, axis="y", alpha=0.25)

# median line + annotation
frac_med = np.searchsorted(tok, med) / n
ax.axvline(med, ls=":", lw=0.9, color=F.OI["black"])
ax.annotate(f"median {med:,} tok", (med + 600, 0.12), fontsize=6.6, color="black", va="center")

# cold-rebuild reference lines at 11k and 28k
for xt, ct in [(11000, cold_11k), (28000, cold_28k)]:
    fr = np.searchsorted(tok, xt) / n
    ax.axvline(xt, ls="--", lw=0.8, color=F.C_COLD, alpha=0.8)
    ax.annotate(f"{xt//1000}k:\ncold rebuild\n{ct:.1f} s",
                (xt - 300, 0.62 if xt == 11000 else 0.42), fontsize=6.2, color=F.C_COLD,
                ha="right", va="center")

pdf, png = F.save(fig, "figM6_workload")

payload = {
    "figure": "M6",
    "message": "On the real robot workload a held history is routinely 10k-30k tokens, so a cold rebuild costs several seconds; keeping it warm is what the paper is about.",
    "source_file": "results/sember/study_e7/e7_requests_h100nvl.jsonl (StudyE7 Job A, D2, answered real questions: grey=False, infeasible=False)",
    "n_questions": n,
    "median_tokens": med,
    "min_tokens": int(tok.min()), "max_tokens": int(tok.max()),
    "report": "reports/study_e7_d2_4b.md section 1 (prompt tokens 511-30,701, p50 10,584)",
    "report_values": {"n": 839, "min": 511, "max": 30701, "p50": 10584},
    "cold_rebuild_anchors_s": {"11k": cold_11k, "28k": cold_28k},
    "cold_rebuild_source": "reports/study_eng1f_disk.md section 5 Part 1 (cold recompute 11k 2.687 s, 28k 7.572 s); ENG1 Part B monolithic 11k 2.755 s cross-check",
    "checks": {"n_ratio": F.ratio(n, 839), "median_ratio": F.ratio(med, 10584),
               "min_match": int(tok.min()) == 511, "max_match": int(tok.max()) == 30701,
               "cold_11k_ratio": F.ratio(cold_11k, 2.687), "cold_28k_ratio": F.ratio(cold_28k, 7.572)},
    "outputs": {"pdf": pdf, "png": png},
}
print(F.dump_json("figM6_workload", payload))
print("M6 done. n", n, "median", med, "range", int(tok.min()), int(tok.max()),
      "anchors", round(cold_11k, 2), round(cold_28k, 2))
