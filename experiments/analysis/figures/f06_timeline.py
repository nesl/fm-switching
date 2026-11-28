#!/usr/bin/env python3
"""Paper F6 (double column): one-run timeline. (a) a normal 1x run, (b) the n20 outage run (14 robots offline 407.5 to
595.5 s, reconnect at 595.5 s). Both are covex-v6-fair-final-cand-tl (DEV), n20, seed 4, 3:11:2 composition, 1200 s.

Per panel, three stacked sub-axes (one y-axis each), 10 s bins:
  occupancy : engine-measured vLLM kv_cache_usage_perc (KV) and kv_offload_cpu_cache_usage_perc (host tier), from
              host_counters_d211.log (sampled about every 10 s; times aligned with run_meta t0_unix). These are
              MEASURED engine fractions, not the planner's belief (the planner's believed host tokens are 0 at every
              decision in both runs).
  decisions : warms = decision.jsonl kind state_action (desired_tier gpu) per bin; touches = kind touch per bin;
              deferrals = kind defer per bin. Warms and touches are 1:1 in every bin in both runs (the two lines
              coincide; checked), so they are drawn as one line.
  late alerts: dashcam alert opportunities delivered after the 1.0 s deadline per bin, by the committed delivery rule
              (d179_rung2_verdict._committed_delivery, _within at 1.0 s), binned by opportunity time. Alerts never
              delivered (about 2,300 to 2,600 per run, declined or infeasible) are NOT counted as late.
OFFLINE, CPU only, read-only on the cells.
"""
import gzip
import json
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import paperstyle as ps
import fig5_11_common as fc

sys.path.insert(0, str(ps.REPO / "experiments/orchestration/live2"))
import d179_rung2_verdict as V  # noqa: E402

STEM = "F06_timeline"
ARM = "covex-v6-fair-final-cand-tl"
RUNS = {
    "a": "covex-v6-fair-final-cand-tl_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30_qp",
    "b": "covex-v6-fair-final-cand-tl_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30_out-k14-d188_evid-t4075_link_qp",
}
OUT_T0, OUT_T1 = 407.5, 595.5
BINS = np.arange(0, 1201, 10)


def load(d):
    p = fc.RUNS / d
    rows = [json.loads(l) for l in gzip.open(p / "decision.jsonl.gz", "rt")]
    t0 = json.load(open(p / "run_meta.json"))["t0_unix"]
    occ = []
    for l in open(p / "host_counters_d211.log"):
        t = float(re.match(r"t=([\d.]+)", l).group(1)) - t0
        g = re.search(r"vllm:kv_cache_usage_perc=([\d.e+-]+)", l)
        h = re.search(r"vllm:kv_offload_cpu_cache_usage_perc=([\d.e+-]+)", l)
        occ.append((t, float(g.group(1)) if g else np.nan, float(h.group(1)) if h else np.nan))
    occ = np.array(occ)
    outs = V._read_jsonl(str(p / "outcomes.jsonl"))
    reqs = V._read_jsonl(str(p / "request.jsonl")) or V._read_jsonl(str(p / "requests.jsonl"))
    dl = V._committed_delivery(outs, reqs)
    al = [o for o in dl.values() if V._type_of(o.get("device_id")) == "alert"]
    late = [float(o["t_opportunity"]) for o in al if o.get("t_delivered") is not None and not V._within(o, 1.0)]
    never = sum(1 for o in al if o.get("t_delivered") is None)
    h = lambda k: np.histogram([r["t"] for r in rows if r["kind"] == k], bins=BINS)[0]
    d = {"occ": occ, "warm": h("state_action"), "touch": h("touch"), "defer": h("defer"),
         "late": np.histogram(late, bins=BINS)[0], "n_alert": len(al), "n_late": len(late), "n_never": never}
    assert (d["warm"] == d["touch"]).all()
    return d


D = {k: load(v) for k, v in RUNS.items()}
BLUE, GREY, INKC = ps.COLORS["covex"], ps.COLORS["stateful"], ps.COLORS["ink"]
mid = BINS[:-1] + 5


def build(fig, mode):
    L, W, G = 0.085, 0.405, 0.035
    tops = [0.93, 0.70, 0.47, 0.24]
    hs = [0.23, 0.23, 0.23, 0.23]
    axes = {}
    for ci, key in enumerate("ab"):
        x0 = L + ci * (W + G + 0.02)
        d = D[key]
        for ri in range(4):
            sh = axes[("a", ri)] if ci == 1 else None
            ax = fig.add_axes([x0, 0.115 + (3 - ri) * 0.215, W, 0.15], sharey=sh)
            axes[(key, ri)] = ax
            ax.axvspan(OUT_T0, OUT_T1, color="#F0E4E4" if key == "b" else "none", lw=0, zorder=0)
            ps.style_axes(ax)
            ax.yaxis.grid(True, color=ps.COLORS["grid"], lw=0.4)
            ax.xaxis.grid(False)
            ax.set_xlim(0, 1200)
            if ri < 3:
                ax.tick_params(labelbottom=False)
            if key == "b":
                ax.tick_params(labelleft=False)
        a0, a1, a2, a3 = (axes[(key, i)] for i in range(4))
        a0.plot(d["occ"][:, 0], d["occ"][:, 1], color=BLUE, lw=0.9, label="KV pool")
        a0.plot(d["occ"][:, 0], d["occ"][:, 2], color=GREY, lw=0.9, label="host tier")
        a1.step(mid, d["warm"], where="mid", color=BLUE, lw=0.9, label="warms")
        a2.bar(mid, d["defer"], width=9, color=INKC, lw=0)
        a3.bar(mid, d["late"], width=9, color=INKC, lw=0)
        a3.set_xlabel("Time (s)", fontsize=ps.FS_AXLABEL, labelpad=2)
        a0.text(0.01, 1.03, "(a) normal 1x run" if key == "a" else "(b) 14-robot outage run, reconnect at 595.5 s",
                transform=a0.transAxes, fontsize=ps.FS_TEXT, color=INKC, ha="left", va="bottom")
        if key == "b":
            for ax in (a0, a1, a2, a3):
                ax.axvline(OUT_T1, color="#B04040", lw=0.7, ls="--", zorder=1)
    axes[("a", 0)].set_ylabel("Occupancy\n(fraction)", fontsize=ps.FS_AXLABEL)
    axes[("a", 1)].set_ylabel("Decisions\nper 10 s", fontsize=ps.FS_AXLABEL)
    axes[("a", 2)].set_ylabel("Deferrals\nper 10 s", fontsize=ps.FS_AXLABEL)
    axes[("a", 3)].set_ylabel("Late alerts\nper 10 s", fontsize=ps.FS_AXLABEL)
    axes[("a", 0)].set_ylim(0, 0.75)
    axes[("a", 1)].set_ylim(0, 200)
    axes[("a", 2)].set_ylim(0, 4)
    axes[("a", 2)].set_yticks([0, 2, 4])
    axes[("a", 3)].set_ylim(0, 14)
    axes[("a", 3)].set_yticks([0, 5, 10])
    axes[("a", 0)].legend(loc="upper left", frameon=False, fontsize=ps.FS_TEXT, ncol=2, handlelength=1.2,
                          bbox_to_anchor=(0.0, 0.98), columnspacing=0.8)
    axes[("a", 1)].text(0.01, 0.97, "warms (each paired with a touch)", transform=axes[("a", 1)].transAxes,
                        fontsize=ps.FS_TEXT, color=BLUE, ha="left", va="top")
    axes[("b", 1)].text(0.5 * (OUT_T0 + OUT_T1), 190, "outage", ha="center", va="top", fontsize=ps.FS_TEXT, color="#B04040")


rows = []
for key, d in RUNS.items():
    m = fc.score_cell(d)
    rows.append({"status": "DEV", "arm": ARM, "panel": key, "seed": 4, "run_dir": m["run_dir"],
                 "run_commit": m["run_commit"], "pipeline_sha": m["pipeline_sha"],
                 "series_files": ["decision.jsonl.gz", "host_counters_d211.log", "outcomes.jsonl", "request.jsonl.gz",
                                  "run_meta.json"],
                 "n_alert_opportunities": D[key]["n_alert"], "n_late_delivered": D[key]["n_late"],
                 "n_alerts_never_delivered": D[key]["n_never"], "n_warms": int(D[key]["warm"].sum()),
                 "n_touches": int(D[key]["touch"].sum()), "n_defers": int(D[key]["defer"].sum())})
body = ("One run on the engine, time on the horizontal axis. (a) A normal run at 1x. (b) The same fleet with 14 of 20 "
        "robots offline from 407.5 s to 595.5 s (shaded; dashed line: reconnect). Top: engine-measured KV pool and "
        "host-tier occupancy. Second and third rows: warm actions (each paired with a touch, so one line) and deferrals per 10 s. Bottom row: alerts "
        "delivered after the 1 s deadline per 10 s (undelivered alerts are not counted).")
cap = fc.finish(STEM, build, ps.DOUBLE_IN, 4.2, ["DEV", "DEV"], rows, body, extra="COVEX dev (cand-tl), n20 seed 4")
print(cap)
for k, d in D.items():
    print(k, d["n_alert"], d["n_late"], d["n_never"], d["warm"].sum(), d["defer"].sum(), d["late"].max(),
          np.nanmax(d["occ"][:, 1]), np.nanmax(d["occ"][:, 2]), d["warm"].max())
