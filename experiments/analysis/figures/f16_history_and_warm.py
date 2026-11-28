#!/usr/bin/env python3
"""Paper Figure 16: (a) accuracy with versus without history, (b) cold vs host-warm vs GPU-warm first-token time.
OFFLINE, committed data only.

(a) 69 EVAL long-history-required (LH-REQ) questions: recent window (last 120 s, "without history") versus full history (D2),
    device Qwen3-VL-4B on the Orin (results/sember/study_orin_rec/orin_rec_part2.jsonl) and cloud 32B instruct on the accuracy
    box (results/sember/study_acc2/acc2_requests.jsonl), LH-REQ ids from results/orchestration/live2/lh_req/lh_req_definition.json.
    Same rule as experiments/figures/fig_m1_lhreq_accuracy.py (over-context rows excluded from the denominator); the script asserts
    the full-suite EVAL counts equal the committed orin_rec_part2_analysis.json (positive control). Wilson 95 percent CIs.
(b) StudyRH5 Part A isolated escalations, Qwen3-VL-32B-Instruct on H100 NVL, vLLM 0.31.0, prefix caching ON: first-token time
    (ttft_s) at ~11k and ~28k prompt tokens. GPU-WARM and HOST-WARM come from the host-offload server (kv-offloading 256 GiB,
    native backend); COLD (cached_tokens 0) comes from the GPU-only server because the host-offload server has no COLD rows.
    Source: results/cost/study_rh5/study_rh5_results_h100nvl.json (partA). These are cost-profile measurements: status
    "cost-profile measurement", not DEV or OLD (committed, current pipeline, not a COVEX arm).
usage: python3 -I f16_history_and_warm.py
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paperstyle as P  # noqa: E402

R = P.REPO
LH = "results/orchestration/live2/lh_req/lh_req_definition.json"
DEV = "results/sember/study_orin_rec/orin_rec_part2.jsonl"
CLOUD = "results/sember/study_acc2/acc2_requests.jsonl"
ANA = "results/sember/study_orin_rec/orin_rec_part2_analysis.json"
RH5 = "results/cost/study_rh5/study_rh5_results_h100nvl.json"


def wilson(k, n, z=1.959963985):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = (z / d) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return p, max(0.0, c - h), min(1.0, c + h)


def cell(data, rep, ids, lh_only):
    sub = [r for r in data if r["rep"] == rep and r["split"] == "EVAL" and (r["question_id"].lower() in ids or not lh_only)]
    ans = [r for r in sub if not r.get("over_context")]
    k = sum(1 for r in ans if r.get("correct"))
    p, lo, hi = wilson(k, len(ans))
    return {"k": k, "n": len(ans), "p": p, "lo": lo, "hi": hi, "over_context": len(sub) - len(ans)}


def jl(p):
    return [json.loads(l) for l in (R / p).read_text().splitlines() if l.strip()]


def main():
    ids = {x.lower() for x in json.loads((R / LH).read_text())["lh_req_question_ids"]}
    dev, cloud = jl(DEV), jl(CLOUD)
    want = json.loads((R / ANA).read_text())["accuracy_by_rep_split_wilson95"]
    for rep in ("RECENT", "D2"):
        c = cell(dev, rep, ids, False)
        assert (c["k"], c["n"]) == (want[f"{rep}_EVAL"]["k"], want[f"{rep}_EVAL"]["n"]), "positive control failed"
    A = {t: {rep: cell(dat, rep, ids, True) for rep in ("RECENT", "D2")} for t, dat in (("device 4B", dev), ("cloud 32B", cloud))}
    rh = json.loads((R / RH5).read_text())
    pa = rh["partA"]
    B = [("COLD", "gpu/COLD"), ("HOST-WARM", "host/HOST-WARM"), ("GPU-WARM", "host/GPU-WARM")]
    sizes = [("11k", "11k tokens"), ("28k", "28k tokens")]
    col = {"COLD": "#C8C8C8", "HOST-WARM": "#7A7A7A", "GPU-WARM": P.COLORS["covex"]}

    def build(fig, mode):
        ax = fig.add_axes([0.085, 0.2, 0.36, 0.74])
        P.style_axes(ax, xgrid=False)
        ax.yaxis.grid(True, color=P.COLORS["grid"], lw=0.4)
        for gi, t in enumerate(A):
            for ri, (rep, fc, a) in enumerate((("RECENT", "#C8C8C8", 1.0), ("D2", P.COLORS["covex"], 1.0))):
                c = A[t][rep]
                x = gi + (ri - 0.5) * 0.38
                ax.bar(x, c["p"], 0.34, color=fc, lw=0)
                ax.plot([x, x], [c["lo"], c["hi"]], color=P.COLORS["ink"], lw=0.8)
                ax.text(x, c["hi"] + 0.015, f"{c['p'] * 100:.0f}", ha="center", va="bottom", fontsize=P.FS_TEXT)
        ax.set_xticks(range(2))
        ax.set_xticklabels(list(A), fontsize=P.FS_TEXT)
        ax.set_ylabel("accuracy, 69 long-history questions", fontsize=P.FS_AXLABEL)
        ax.set_ylim(0, 0.8)
        ax.set_xlim(-0.6, 1.6)
        from matplotlib.patches import Patch
        ax.legend([Patch(fc="#C8C8C8"), Patch(fc=P.COLORS["covex"])], ["recent window (no history)", "full history"],
                  loc="upper left", fontsize=P.FS_TEXT, frameon=False, handlelength=1.0, borderaxespad=0.1)
        bx = fig.add_axes([0.58, 0.2, 0.4, 0.74])
        P.style_axes(bx, xgrid=False)
        bx.yaxis.grid(True, color=P.COLORS["grid"], lw=0.4)
        bx.set_yscale("log")
        for gi, (sk, _) in enumerate(sizes):
            for bi, (name, key) in enumerate(B):
                v = pa[f"{key}/{sk}"]["ttft_s"]
                x = gi + (bi - 1) * 0.27
                bx.bar(x, v["median"], 0.25, color=col[name], lw=0, label=name if gi == 0 else None)
                pts = pa[f"{key}/{sk}"]["ttft_all"]
                bx.plot([x] * 2, [min(pts), max(pts)], color=P.COLORS["ink"], lw=0.8)
                bx.text(x, max(pts) * 1.12, f"{v['median']:.2f}", ha="center", va="bottom", fontsize=P.FS_TEXT - 0.5)
        bx.set_xticks(range(2))
        bx.set_xticklabels([s[1] for s in sizes], fontsize=P.FS_TEXT)
        bx.set_ylabel("first-token time (s)", fontsize=P.FS_AXLABEL)
        bx.set_ylim(0.2, 20)
        bx.set_yticks([0.3, 1, 3, 10])
        bx.set_yticklabels(["0.3", "1", "3", "10"])
        bx.set_xlim(-0.6, 1.6)
        bx.legend(loc="upper left", fontsize=P.FS_TEXT, frameon=False, handlelength=1.0, ncol=3, columnspacing=0.8,
                  borderaxespad=0.1)
        fig.text(0.003, 0.985, "(a)", fontsize=P.FS_AXLABEL, fontweight="bold", va="top")
        fig.text(0.50, 0.985, "(b)", fontsize=P.FS_AXLABEL, fontweight="bold", va="top")

    caption = ("(a) Accuracy on the 69 EVAL long-history-required questions with the recent window only versus the full "
               "history, for the on-device 4B model and the cloud 32B model (Wilson 95 percent bands, each question one trial). "
               "(b) First-token time of an isolated 32B escalation when the prefix is cold, in host memory, or on the GPU, at about "
               "11k and 28k prompt tokens (bars are medians, whiskers min to max over 12 and 6 requests). The cold series comes "
               "from the GPU-only server and the two warm series from the host-offload server of the same study. "
               "Both panels are committed cost-profile and accuracy measurements, not COVEX system results.")
    rows = [{"status": "committed measurement (no OLD/DEV arm)", "panel": "a", "tier": t, "rep": rep, **A[t][rep],
             "run_dir": f"{DEV if t.startswith('device') else CLOUD}; {LH}", "run_commit": "see experiments/figures M1 caption (1acbe36, c31ea43, 6b3a173)",
             "pipeline_sha": "n/a"} for t in A for rep in A[t]]
    rows += [{"status": "cost-profile measurement (not DEV/OLD)", "panel": "b", "state": name, "size": sk, "source_key": f"partA/{key}/{sk}",
              "n": pa[f"{key}/{sk}"]["ttft_s"]["n"], "ttft_median_s": pa[f"{key}/{sk}"]["ttft_s"]["median"],
              "ttft_min_s": pa[f"{key}/{sk}"]["ttft_s"]["min"], "ttft_max_s": pa[f"{key}/{sk}"]["ttft_s"]["max"],
              "run_dir": RH5, "run_commit": rh["_provenance"]["git_commit"], "pipeline_sha": "n/a"} for name, key in B for sk, _ in sizes]
    P.save_figure(build, "F16_history_and_warm", P.DOUBLE_IN, 2.5, [], rows, caption, None)
    (P.OUTDIR / "F16_history_and_warm.caption.txt").write_text(
        "[PLACEHOLDER: committed accuracy and cost-profile measurements, no COVEX data, not FINAL] " + caption + "\n")
    j = json.loads((P.OUTDIR / "F16_history_and_warm.rows.json").read_text())
    j["status_tag"] = "committed measurements (cost-profile and S-EMBER accuracy); no OLD/DEV arm plotted"
    j["positive_control"] = "full-suite EVAL device counts equal committed orin_rec_part2_analysis.json"
    (P.OUTDIR / "F16_history_and_warm.rows.json").write_text(json.dumps(j, indent=1))
    P.compile_preview("F16_history_and_warm", caption)
    print(json.dumps(A, indent=0)[:600])


if __name__ == "__main__":
    main()
