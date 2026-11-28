#!/usr/bin/env python3
"""Paper Figure 12 (network outage and reconnect), D322-D337. OFFLINE, CPU only, committed cells only.

Reads, per cell, outcomes.jsonl (one row per opportunity: kind, device_id, t_opportunity, within_L), cell.json and
link_events.json (outage window) under results/orchestration/live2/frozen_test/runs. Cells (all n20, seed 4, 14
robots in outage, outage [407.5, 595.5] s, d = 188 s, evidence placement t4075):
  rung 3  covex-v6-fair-final                  (OLD)   control: no-outage cell of the same arm
  eager   covex-v6-fair-final-cand-tl-sync-eager (OLD, not a DEV arm) control: none committed
  F0 no S2 covex-v6-fair-final-cand-tl         (DEV)   control: no-outage cell of the same arm
  F0 + S2 covex-v6-fair-final-cand-tl-sync     (DEV)   control: none committed (sync-cf no-outage is a different arm)
Type = single-shot (device asst*), robot (device robo*), dashcam (kind monitor). On time = the committed within_L flag.
Panel (a): on-time rate in 10 s bins of t_opportunity from R-60 to R+300 (R = 595.5 s, the reconnect). Panel (b):
whole-run and [R, R+120] on-time rate per type. usage: python3 -I f12_network.py
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paperstyle as P  # noqa: E402

RUNS = P.REPO / "results/orchestration/live2/frozen_test/runs"
SUF = "_1200s_h27_3t_c3-11-2_L3_epg_rq30"
OUT = "_out-k14-d188_evid-t4075_link"
ARMS = [  # key, short tick, arm, outage dir, control dir, colour, legend label, status
    ("rung3", "rung 3", P.COVEX_RUNG3, f"covex-v6-fair-final_n20_s4{SUF}{OUT}",
     f"covex-v6-fair-final_n20_s4{SUF}", "#9DB4CE", P.legend_label(P.COVEX_RUNG3)),
    ("eager", "eager", "covex-v6-fair-final-cand-tl-sync-eager",
     f"covex-v6-fair-final-cand-tl-sync-eager_n20_s4{SUF}{OUT}_qp", None, "#6F93BA", "COVEX eager (old)"),
    ("f0", "no S2", "covex-v6-fair-final-cand-tl", f"covex-v6-fair-final-cand-tl_n20_s4{SUF}{OUT}_qp",
     f"covex-v6-fair-final-cand-tl_n20_s4{SUF}_qp", P.COLORS["covex"], "COVEX, no S2 (dev)"),
    ("f0s2", "+ S2", "covex-v6-fair-final-cand-tl-sync", f"covex-v6-fair-final-cand-tl-sync_n20_s4{SUF}{OUT}_qp",
     None, "#10294A", P.legend_label("covex-v6-fair-final-cand-tl-sync")),
]
TYPES = [("single-shot", "Single-shot"), ("robot", "Robot follow-up"), ("dash", "Dashcam")]
WIN = 120.0
EDGES = None


def typ(r):
    if r["kind"] == "monitor":
        return "dash"
    return "robot" if r["device_id"].startswith("robo") else "single-shot"


def load(d):
    rows = [json.loads(l) for l in open(RUNS / d / "outcomes.jsonl")]
    return [(typ(r), float(r["t_opportunity"]), bool(r["within_L"])) for r in rows]


def reconnect(d):
    c = json.loads((RUNS / d / "cell.json").read_text())
    return c


def stats(rows, R):
    edges = np.arange(R - 60, R + 300 + 1e-9, 10.0)
    out = {}
    for t, _ in TYPES:
        x = np.array([(a, b) for ty, a, b in rows if ty == t], dtype=float)
        ts, ok = x[:, 0], x[:, 1]
        k = np.full(len(edges) - 1, np.nan)
        n = np.zeros(len(edges) - 1, int)
        for i in range(len(edges) - 1):
            m = (ts >= edges[i]) & (ts < edges[i + 1])
            n[i] = int(m.sum())
            if n[i]:
                k[i] = ok[m].mean()
        w = (ts >= R) & (ts < R + WIN)
        out[t] = {"bin_rate": k, "bin_n": n, "whole": float(ok.mean()), "whole_n": int(len(ts)),
                  "win": float(ok[w].mean()) if w.any() else float("nan"), "win_n": int(w.sum())}
    return edges, out


def main():
    data, rows_json, statuses = {}, [], []
    R = None
    for key, short, arm, od, cd, col, lab in ARMS:
        le = json.loads((RUNS / od / "link_events.json").read_text())
        o = le["outage"]
        assert o["t_start"] == 407.5 and o["t_end"] == 595.5 and len(o["robots"]) == 14, (od, o["t_start"], o["t_end"])
        R = o["t_end"]
        edges, s = stats(load(od), R)
        sc = None
        if cd:
            _, sc = stats(load(cd), R)
        data[key] = (s, sc)
        st = P.arm_status(arm, "valid")
        statuses.append(st)
        for d, kind in ((od, "outage"), (cd, "control")):
            if d is None:
                continue
            cj = json.loads((RUNS / d / "cell.json").read_text())
            rm = json.loads((RUNS / d / "run_meta.json").read_text())
            rows_json.append({"status": st, "arm": arm, "seed": 4, "condition": kind, "n_devices": 20,
                              "run_dir": str(Path("results/orchestration/live2/frozen_test/runs") / d),
                              "run_commit": rm.get("git_commit"), "pipeline_sha": "none (not in figdata; read "
                              "outcomes.jsonl within_L)", "run_valid": cj.get("run_valid"),
                              "on_time_rule": cj["score"]["score"].get("on_time_rule", "")[:80],
                              "whole_run": {t: [data[key][0 if kind == "outage" else 1][t]["whole"],
                                                data[key][0 if kind == "outage" else 1][t]["whole_n"]]
                                            for t, _ in TYPES},
                              "window_R_R120": {t: [data[key][0 if kind == "outage" else 1][t]["win"],
                                                    data[key][0 if kind == "outage" else 1][t]["win_n"]]
                                                for t, _ in TYPES}})
    # positive control: robot and single-shot whole-run vs the committed score block of the F0 outage cell
    cj = json.loads((RUNS / ARMS[2][3] / "cell.json").read_text())["score"]["score"]
    chk = {"committed_robot_pool_fraction": cj["robot_headline"]["on_time_beside_it"]["robot_pool_fraction"],
           "this_robot_whole": data["f0"][0]["robot"]["whole"],
           "committed_ss_on_time_fraction": cj["assistive_value"]["on_time_fraction"],
           "this_ss_whole": data["f0"][0]["single-shot"]["whole"]}

    def build(fig, mode):
        P.style_axes  # noqa
        gs = fig.add_gridspec(2, 3, left=0.085, right=0.985, top=0.95, bottom=0.17, hspace=0.5, wspace=0.14)
        x = (edges[:-1] + 5) - R
        for j, (t, tname) in enumerate(TYPES):
            ax = fig.add_subplot(gs[0, j])
            P.style_axes(ax)
            ax.axvspan(-60, 0, color="#EDEDED", lw=0)
            for key, short, arm, od, cd, col, lab in ARMS:
                s, sc = data[key]
                ax.plot(x, s[t]["bin_rate"], color=col, lw=0.7, marker="o", ms=1.5, label=lab)
                if sc is not None and t == "dash":
                    ax.plot(x, sc[t]["bin_rate"], color=col, lw=0.6, ls=(0, (2, 2)), alpha=0.9)
            ax.axvline(0, color=P.COLORS["ink"], lw=0.5)
            ax.set_xlim(-60, 300)
            ax.set_ylim(-0.03, 1.05)
            ax.set_xticks([-60, 0, 100, 200, 300])
            ax.yaxis.grid(True, color=P.COLORS["grid"], lw=0.4)
            if j:
                ax.set_yticklabels([])
            else:
                ax.set_ylabel("on-time rate", fontsize=P.FS_AXLABEL)
            ax.set_xlabel("s from reconnect R", fontsize=P.FS_AXLABEL)
            ax.text(0.98, 0.04, tname, transform=ax.transAxes, fontsize=P.FS_TEXT, va="bottom", ha="right",
                    color=P.COLORS["ink"], bbox=dict(fc="white", ec="none", alpha=0.85, pad=1.0))
            ax.text(-30, 1.03, "outage", fontsize=5.5, ha="center", va="bottom", color="#777777")
        for j, (t, tname) in enumerate(TYPES):
            ax = fig.add_subplot(gs[1, j])
            P.style_axes(ax, xgrid=False)
            ax.yaxis.grid(True, color=P.COLORS["grid"], lw=0.4)
            for i, (key, short, arm, od, cd, col, lab) in enumerate(ARMS):
                s, sc = data[key]
                ax.bar(i - 0.2, s[t]["whole"], 0.36, color=col, alpha=0.45, lw=0)
                ax.bar(i + 0.2, s[t]["win"], 0.36, color=col, lw=0)
                if sc is not None:
                    ax.plot([i + 0.02, i + 0.38], [sc[t]["win"]] * 2, color=P.COLORS["ink"], lw=0.9)
                    ax.plot([i - 0.38, i - 0.02], [sc[t]["whole"]] * 2, color=P.COLORS["ink"], lw=0.9)
            ax.set_xticks(range(len(ARMS)))
            ax.set_xticklabels([a[1] for a in ARMS], fontsize=P.FS_TEXT)
            ax.set_ylim(0, 1.05)
            ax.set_xlim(-0.6, len(ARMS) - 0.4)
            if j:
                ax.set_yticklabels([])
            else:
                ax.set_ylabel("on-time rate", fontsize=P.FS_AXLABEL)
        fig.text(0.003, 0.985, '(a)', fontsize=P.FS_AXLABEL, fontweight='bold', va='top')
        fig.text(0.003, 0.49, '(b)', fontsize=P.FS_AXLABEL, fontweight='bold', va='top')
        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch
        h = [Line2D([0], [0], color=a[5], lw=1.2, marker="o", ms=2) for a in ARMS]
        l = [a[6] for a in ARMS]
        h += [Line2D([0], [0], color="#555555", lw=0.6, ls=(0, (2, 2))), Line2D([0], [0], color="k", lw=0.9),
              Patch(facecolor="#777777", alpha=0.45), Patch(facecolor="#777777")]
        l += ["no-outage control, dashcam (a)", "no-outage control (b)", "whole run", "R to R+120 s"]
        fig.legend(h, l, loc="lower center", ncol=4, fontsize=P.FS_TEXT, frameon=False, handlelength=1.6,
                   columnspacing=1.0, bbox_to_anchor=(0.5, 0.0))

    caption = ("Network outage and reconnect, 20 devices, seed 4, 14 robots offline for d = 188 s (outage ends at "
               "the reconnect R = 595.5 s). (a) On-time rate in 10 s bins of request time from R-60 s to R+300 s per "
               "request type; the dashed lines on the dashcam panel are the same arm without the outage where a cell exists (omitted for the sparse robot and single-shot types). Robot and "
               "single-shot bins hold 0 to a few requests each, so those series are noisy and bins with no request "
               "are left blank. (b) Whole-run (light) and R to R+120 s (dark) on-time rate; black ticks mark the "
               "no-outage control. On time is the committed within-L flag of each request.")
    extra = ("n20 seed 4 only; seeds 5-7 outage cells not committed; eager and F0 + S2 have no no-outage control; "
             "rung 3 and eager are OLD, F0 and F0 + S2 are DEV")
    P.save_figure(build, "F12_network", P.DOUBLE_IN, 3.9, statuses, rows_json, caption, extra)
    # attach checks to rows.json
    rj = P.OUTDIR / "F12_network.rows.json"
    j = json.loads(rj.read_text())
    j["positive_control_vs_committed_score_block"] = chk
    j["per_bin_n"] = {k: {t: data[k][0][t]["bin_n"].tolist() for t, _ in TYPES} for k in data}
    rj.write_text(json.dumps(j, indent=1, default=str))
    print(json.dumps(chk, indent=1))
    pdf = P.compile_preview("F12_network", caption.replace("%", r"\%"))
    print(pdf)


if __name__ == "__main__":
    main()
