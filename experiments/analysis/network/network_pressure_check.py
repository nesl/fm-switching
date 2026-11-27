#!/usr/bin/env python3
"""Network pressure check for the post-reconnect sync regime (D322). OFFLINE, CPU only, read-only.

Correlated whole-site outage: all robots lose the uplink for d seconds from t0; robot frames offered in
[t0, t0 + d) are buffered and drain at reconnect R = t0 + d (buffered semantics). Questions asked during
the outage are device-only (D242) and are counted, not served. The burst of eager sync occupies the cloud
for B seconds after R, competing with single-shot questions, robot follow-ups and dashcam frames.

Inputs: the committed trace code (fleet/trace.py) run AS COMMITTED for the no-outage control trace, seed 4,
mix 3:11:2 (tag _c3-11-2), 1200 s, mode A, per-frame robot upload, L3_epg_rq30 settings. Backlog comes from the
trace's own history_batch records (est_tokens, frame_bytes 24570); question and frame times are the trace's.
No trace or committed module is modified.

Bounds on the burst B (seconds):
  FAST = total backlog tokens / 17,945.2 tok/s (oracle_lp_run.py:30, D230 (12) measured peak).
  SLOW = sum over victims of baselines/costs.py recall_ttft_s(backlog_r, "COLD") (committed cold prefill rule).
  REBUILD (sensitivity, not a bound) = sum over victims of recall_ttft_s(full history at R, "COLD").
A start t0 is accepted for a bound when t0 + d + B <= 1200.

Bar (pre-registered, do not change): PRESSURE at FAST iff median over accepted t0 of (single-shot + robot
follow-up questions inside [R, R+B)) >= 15 AND median over accepted t0 of B_FAST >= 4.0 s.
Placement: passing starts are the t0 where the two FAST conditions hold for that start; the token is the median
passing start in tenths of a second (`_evid-t<tenths>`), by analogy with the committed B2 rule.
"""
from __future__ import annotations
import bisect, json, sys
from pathlib import Path
import numpy as np

REPO = Path("/home/nesl/fm-switching")
for p in ("experiments/orchestration/live2/fleet", "experiments/orchestration/baselines", "experiments/lib"):
    sys.path.insert(0, str(REPO / p))
import trace as TR  # noqa: E402
import costs as CO  # noqa: E402
from _provenance import stamp  # noqa: E402

RATE_FAST = 17945.2             # oracle_lp_run.py:30
KV_BYTES_PER_TOKEN = 262144     # baselines/costs.py:90 (HOST_BYTES_PER_TOKEN); bf16 KV per launch config
GIB = 1024 ** 3
OVER32K = 32768
BAR_Q, BAR_B = 15, 4.0
SEED = 4
MIX = "3:11:2"

CONDITIONS = [
    ("C1", 20, 188.0, "outage n20 all-robots d188"),
    ("C2", 32, 188.0, "outage n32 all-robots d188"),
    ("C3", 20, 300.0, "outage n20 all-robots d300"),
]


def trace_for(n):
    return TR.generate_trace(seed=SEED, n_devices=n, ratio=MIX, run_s=1200.0, mode="A",
                             robot_question_set="lh_req", ss_question_set="ss2", dashcam_format="epg",
                             robot_upload="per-frame", robot_reask_mean_s=30.0)["records"]


def index(recs):
    robots = sorted({r["device_id"] for r in recs if str(r["device_id"]).startswith("robo")})
    hb = {d: [] for d in robots}
    for r in recs:
        if r["kind"] == "history_batch" and r["device_id"] in hb:
            hb[r["device_id"]].append((float(r["t"]), int(r["est_tokens"]), int(r["cum_tokens"])))
    for d in hb:
        hb[d].sort()
    t_hb = {d: [x[0] for x in hb[d]] for d in hb}
    rq_robo, rq_asst, rq_hist = [], [], []
    dash = []
    for r in recs:
        if r["kind"] == "recall_question":
            if str(r["device_id"]).startswith("robo"):
                rq_robo.append((float(r["t"]), int(r["history_tokens"]), r["device_id"]))
            elif str(r["device_id"]).startswith("asst"):
                rq_asst.append(float(r["t"]))
        elif r["kind"] == "monitor_opportunity" and str(r["device_id"]).startswith("dash"):
            dash.append(float(r["t"]))
    rq_robo.sort()
    return {"robots": robots, "hb": hb, "t_hb": t_hb, "rq_robo": rq_robo,
            "rq_robo_t": [x[0] for x in rq_robo], "rq_asst": sorted(rq_asst), "dash": sorted(dash)}


def count(sorted_list, a, b):
    return bisect.bisect_left(sorted_list, b) - bisect.bisect_left(sorted_list, a)


def backlog_window(ix, t0, d):
    """per-victim backlog tokens of frames captured in [t0, t0+d) (the trace's own est_tokens)."""
    out = {}
    for dev in ix["robots"]:
        ts = ix["t_hb"][dev]
        lo, hi = bisect.bisect_left(ts, t0), bisect.bisect_left(ts, t0 + d)
        out[dev] = sum(x[1] for x in ix["hb"][dev][lo:hi])
    return out


def full_history_at(ix, R):
    """per-victim cumulative tokens of the session at reconnect (last cum_tokens before R)."""
    out = {}
    for dev in ix["robots"]:
        ts = ix["t_hb"][dev]
        i = bisect.bisect_left(ts, R)
        out[dev] = ix["hb"][dev][i - 1][2] if i > 0 else 0
    return out


def cold_time(tokens):
    return CO.recall_ttft_s(int(tokens), "COLD") if tokens > 0 else 0.0


def sweep(ix, d):
    rows = []
    for t0 in np.arange(0.0, 1200.0, 1.0):
        t0 = float(t0)
        bl = backlog_window(ix, t0, d)
        total = sum(bl.values())
        R = t0 + d
        B = {"FAST": total / RATE_FAST,
             "SLOW": sum(cold_time(v) for v in bl.values())}
        fh = full_history_at(ix, R)
        B["REBUILD"] = sum(cold_time(fh[dev]) for dev in ix["robots"])
        row = {"t0": t0, "backlog_total_tokens": total,
               "backlog_per_victim_mean": total / max(len(ix["robots"]), 1),
               "outage_robot_questions": count(ix["rq_robo_t"], t0, R), "bounds": {}}
        for name, b in B.items():
            if R + b > 1200.0 - 1e-9 or t0 + d + b > 1200.0 + 1e-9:
                continue
            sq = count(ix["rq_asst"], R, R + b)
            fu = count(ix["rq_robo_t"], R, R + b)
            dsh = count(ix["dash"], R, R + b)
            row["bounds"][name] = {"B_s": b, "single_shot": sq, "robot_followups": fu,
                                   "dash_frames": dsh, "sq_plus_fu": sq + fu}
        rows.append(row)
    return rows


def stats(vals):
    v = np.array(vals, float)
    if v.size == 0:
        return None
    return {"median": float(np.median(v)), "p10": float(np.percentile(v, 10)),
            "p90": float(np.percentile(v, 90)), "n_starts": int(v.size)}


def summarise(rows, name):
    sel = [r for r in rows if name in r["bounds"]]
    if not sel:
        return None
    sqfu = [r["bounds"][name]["sq_plus_fu"] for r in sel]
    B = [r["bounds"][name]["B_s"] for r in sel]
    return {"bound": name, "sq_plus_fu": stats(sqfu), "burst_B_s": stats(B),
            "single_shot": stats([r["bounds"][name]["single_shot"] for r in sel]),
            "robot_followups": stats([r["bounds"][name]["robot_followups"] for r in sel]),
            "dash_frames": stats([r["bounds"][name]["dash_frames"] for r in sel]),
            "outage_robot_questions": stats([r["outage_robot_questions"] for r in sel])}


def placement(rows):
    passing = [r["t0"] for r in rows if "FAST" in r["bounds"]
               and r["bounds"]["FAST"]["sq_plus_fu"] >= BAR_Q and r["bounds"]["FAST"]["B_s"] >= BAR_B]
    if not passing:
        return {"passing_starts": 0, "median_t0": None, "token": None}
    m = float(np.median(passing))
    return {"passing_starts": len(passing), "median_t0": m, "token": f"_evid-t{int(round(m * 10))}"}


def over32k(ix, rows, d):
    """Robot questions asked after reconnect whose history, plus the victim's lost-window backlog, exceeds
    32,768 tokens, while the no-outage history does not. Returns the median over accepted starts and the
    no-outage count of questions already over 32,768 (the committed exclusions)."""
    already = sum(1 for _, h, _ in ix["rq_robo"] if h > OVER32K)
    added_by_t0 = []
    for r in rows:
        t0 = r["t0"]; R = t0 + d
        bl = backlog_window(ix, t0, d)
        added = sum(1 for t, h, dev in ix["rq_robo"]
                    if t >= R and h <= OVER32K and h + bl.get(dev, 0) > OVER32K)
        added_by_t0.append(added)
    return {"already_over_32k_no_outage": already, "added_by_outage": stats(added_by_t0)}


def main():
    out = {"_what": "Network pressure check, post-reconnect sync regime (D322), CPU only, committed code, "
                    "seed 4, mix 3:11:2. Bar pre-registered; not part of the bar: SLOW and REBUILD.",
           "rate_fast_tok_s": RATE_FAST, "kv_bytes_per_token": KV_BYTES_PER_TOKEN, "bar": {
               "pressure_iff": "median sq+fu >= 15 AND median B_FAST >= 4.0 s", "q": BAR_Q, "b": BAR_B},
           "conditions": {}}
    for cname, n, d, label in CONDITIONS:
        recs = trace_for(n)
        ix = index(recs)
        rows = sweep(ix, d)
        fast = summarise(rows, "FAST")
        slow = summarise(rows, "SLOW")
        rebuild = summarise(rows, "REBUILD")
        bar_pass = bool(fast and fast["sq_plus_fu"]["median"] >= BAR_Q and fast["burst_B_s"]["median"] >= BAR_B)
        pl = placement(rows)
        backlog_tot = [r["backlog_total_tokens"] for r in rows]
        kv_gib = [t * KV_BYTES_PER_TOKEN / GIB for t in backlog_tot]
        o32 = over32k(ix, [r for r in rows if "FAST" in r["bounds"]], d)   # accepted FAST starts only
        out["conditions"][cname] = {
            "label": label, "n_devices": n, "d_s": d, "robots_k_all": len(ix["robots"]),
            "robot_frame_bytes": 24570, "robot_tokens_per_frame": 90,
            "backlog_total_tokens": stats(backlog_tot),
            "backlog_per_victim_tokens": stats([r["backlog_per_victim_mean"] for r in rows]),
            "kv_demand_GiB": stats(kv_gib),
            "FAST": fast, "SLOW_not_bar": slow, "REBUILD_sensitivity": rebuild,
            "bar_result": "PASS" if bar_pass else "FAIL",
            "placement": pl, "over_32k": o32,
            "n_accepted_starts": {b: sum(1 for r in rows if b in r["bounds"]) for b in ("FAST", "SLOW", "REBUILD")}}
    out["_provenance"] = stamp(script="network_pressure_check.py", model="none", device="jetson_orin")
    dst = REPO / "results/orchestration/live2/network_pressure/network_pressure_check.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, indent=1, default=float))
    for c, v in out["conditions"].items():
        f = v["FAST"]
        print(c, v["bar_result"], "median sq+fu", f and f["sq_plus_fu"]["median"],
              "median B", f and round(f["burst_B_s"]["median"], 3), "placement", v["placement"]["token"])


if __name__ == "__main__":
    main()
