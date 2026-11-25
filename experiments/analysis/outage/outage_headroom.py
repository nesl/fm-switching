#!/usr/bin/env python3
"""StudyOUTAGE-HEADROOM (PRELIMINARY, offline, CPU, read-only, NO PLOT).

Pre-registration: reports/study_outage_headroom.md (committed cd8f6eb7).
Question: after a network outage, is the reconnect burst big enough that the ORDER of recovery
(FIFO replay of the backlog vs an ideal deadline-first order) can change the number of on-time
CORRECT cloud answers? Headroom = the MOST an ideal order could save over FIFO inside the recovery
window; an upper bound (necessary condition), not an achieved value.

Everything is derived from the committed s4 trace (fairness-digest-validated) and committed
constants. No new runs, no cells, no plot. Values -> reports/figures/outage_headroom_results.json
and reports/study_outage_headroom_results.md.
"""
import sys, os, json, collections
from pathlib import Path

ROOT = Path("/home/nesl/fm-switching")
sys.path.insert(0, str(ROOT / "experiments/orchestration/live2/fleet"))
sys.path.insert(0, str(ROOT / "experiments/lib"))
import trace as TR
from _provenance import stamp

# ---- committed constants ----
TRACE_ARGS = dict(seed=4, n_devices=16, ratio="40:40:20", run_s=1200.0, mode="A",
                  robot_question_set="lh_req", ss_question_set="ss2",
                  dashcam_format="epg", robot_upload="per-frame", robot_reask_mean_s=30.0)
COMMITTED_DIGEST = "96c1a0b486381709e2fc63e9b0f33f9e1ba1d887d6cedf21d89d407621177849"
RUN_S = 1200.0

T_PEAK = 17945.2            # tok/s, 1x peak uncached prefill (D230 (12))
RTT_MS = 44.0              # D75
NET_S = (RTT_MS / 1000.0) / 2.0   # one-way minimum delivery = RTT/2
UPLINK = {"default_13.6Mbit": 13.6, "low_0.9Mbit_PROVISIONAL": 0.9}   # Mbit/s (D75 / StudyNET-TIER1)
BYTES_PER_FRAME = {"dashcam": 62670.12, "robot": 24486.86, "single-shot": 24486.86}  # committed manifests
QUESTION_TEXT_B = 1200     # committed fleet/emulator.py:73
EPG_TEXT = TR.EPG_TEXT_TOKENS       # 42
EPG_PER_FRAME = TR.EPG_TOK_PER_FRAME  # 338
DECODE = 2
DEADLINE_S = {"dashcam": 1.0, "robot": 3.0, "single-shot": 2.0}

OUTAGE_LENGTHS = [30.0, 10.0, 60.0]
STARTS = [RUN_S * k / 6.0 for k in range(1, 6)]   # 200,400,600,800,1000


def dtype(dev):
    s = str(dev)
    if s.startswith("robo"): return "robot"
    if s.startswith("asst"): return "single-shot"
    if s.startswith("dash"): return "dashcam"
    return "other"


def uplink_bps(mbps):
    return mbps * 1e6 / 8.0   # bytes/s (committed cstate.py:628)


def d162_ttft(uncached, queued_ahead=0.0):
    return 0.0678 + 0.000182 * uncached + 0.000154 * queued_ahead


def build_index(recs):
    """Per-device, time-sorted monitor instants and recall questions."""
    mons = collections.defaultdict(list)
    recalls = collections.defaultdict(list)
    hbatch = collections.defaultdict(list)
    for r in recs:
        k = r["kind"]
        if k == "monitor_opportunity":
            mons[r["device_id"]].append(r)
        elif k == "recall_question":
            recalls[r["device_id"]].append(r)
        elif k == "history_batch":
            hbatch[r["device_id"]].append(r)
    for d in mons: mons[d].sort(key=lambda r: r["t"])
    for d in recalls: recalls[d].sort(key=lambda r: r["t"])
    for d in hbatch: hbatch[d].sort(key=lambda r: r["t"])
    return mons, recalls, hbatch


def offline_sets(devs_by_type):
    """Deterministic, recorded offline-device membership."""
    robot = sorted(devs_by_type["robot"])
    dash = sorted(devs_by_type["dashcam"])
    ss = sorted(devs_by_type["single-shot"])
    sets = {"robot1": [robot[0]], "dashcam1": [dash[0]]}
    # correlated K: round-robin across [robot, dashcam, single-shot]
    pools = {"robot": list(robot), "dashcam": list(dash), "single-shot": list(ss)}
    order = ["robot", "dashcam", "single-shot"]
    for K in (2, 4, 7):
        picked, idx = [], {t: 0 for t in order}
        i = 0
        while len(picked) < K:
            t = order[i % 3]
            if idx[t] < len(pools[t]):
                picked.append(pools[t][idx[t]]); idx[t] += 1
            i += 1
            if i > 100: break
        sets[f"K{K}"] = picked
    return sets


def device_backlog(dev, t0, t1, mons, recalls, hbatch):
    """Backlog accumulated on ONE offline device during [t0, t1], and the cold-rebuild work for the
    first decision at/after reconnect t1. Upload = frames captured during the outage (bytes).
    Cold rebuild = full uncached prefill of the next decision (KV lost on disconnect)."""
    typ = dtype(dev)
    bpf = BYTES_PER_FRAME[typ]
    out = {"device": dev, "type": typ, "buffered_frames": 0, "upload_bytes": 0.0,
           "cold_rebuild_tokens": 0, "next_decision_t": None}
    if typ == "dashcam":
        inst = mons.get(dev, [])
        win = [r for r in inst if t0 <= r["t"] < t1]
        out["buffered_frames"] = len(win)          # 1 new frame per 0.5 s instant
        out["upload_bytes"] = len(win) * bpf
        nxt = next((r for r in inst if r["t"] >= t1), None)
        if nxt is not None:
            ef = int(nxt.get("episode_frames", 1))
            out["cold_rebuild_tokens"] = EPG_TEXT + EPG_PER_FRAME * ef + DECODE
            out["next_decision_t"] = nxt["t"]
    else:
        # robot / single-shot: frames arrive as history batches; question text is tiny
        hb = [r for r in hbatch.get(dev, []) if t0 <= r["t"] < t1]
        nfr = sum(len(r.get("frame_refs", []) or []) for r in hb)
        q_in = [r for r in recalls.get(dev, []) if t0 <= r["t"] < t1]
        out["buffered_frames"] = nfr
        out["upload_bytes"] = nfr * bpf + len(q_in) * QUESTION_TEXT_B
        nxt = next((r for r in recalls.get(dev, []) if r["t"] >= t1), None)
        if nxt is not None:
            out["cold_rebuild_tokens"] = int(nxt.get("history_tokens", 0)) + DECODE
            out["next_decision_t"] = nxt["t"]
    return out


def in_window_decisions(recs_idx, t1, R):
    """Decisions from ALL devices whose DEADLINE falls in [t1, t1+R], in D192 units.
    Returns per-type counts and the fit-limited subset (served on time if prioritized at T)."""
    mons, recalls, _ = recs_idx
    lo, hi = t1, t1 + R
    counts = {"dashcam": 0, "robot": 0, "single-shot": 0}
    fit = {"dashcam": 0, "robot": 0, "single-shot": 0}
    # recall (robot + single-shot): unit = one question
    for dev, qs in recalls.items():
        typ = dtype(dev); L = DEADLINE_S[typ]
        for r in qs:
            ddl = r["t"] + r.get("deadline_s", L)
            if lo <= ddl <= hi:
                counts[typ] += 1
                w = int(r.get("history_tokens", 0)) + DECODE
                if w / T_PEAK + NET_S <= L + 1e-9:
                    fit[typ] += 1
    # dashcam: unit = EPISODE (in-window if ANY instant's deadline is in window)
    ep_in, ep_fit = {}, {}
    for dev, inst in mons.items():
        for r in inst:
            ddl = r["t"] + r.get("deadline_s", 1.0)
            if lo <= ddl <= hi:
                eid = r.get("episode_id")
                ep_in[eid] = True
                w = EPG_TEXT + EPG_PER_FRAME * int(r.get("episode_frames", 1)) + DECODE
                if w / T_PEAK + NET_S <= DEADLINE_S["dashcam"] + 1e-9:
                    ep_fit[eid] = True
    counts["dashcam"] = len(ep_in)
    fit["dashcam"] = len(ep_fit)
    return counts, fit


def verdict(R):
    if R < 1.0: return "NO ROOM (<1 s)"
    if R <= 10.0: return "SOME ROOM (1-10 s)"
    return "LARGE ROOM (>10 s)"


def run():
    b = TR.generate_trace(**TRACE_ARGS)
    recs = b["records"]
    dig = TR.fairness_digest(recs, "A")
    assert dig == COMMITTED_DIGEST, f"TRACE DIGEST MISMATCH {dig} -> STOP"
    mons, recalls, hbatch = build_index(recs)
    recs_idx = (mons, recalls, hbatch)
    devs_by_type = collections.defaultdict(set)
    for r in recs:
        if "device_id" in r and dtype(r["device_id"]) != "other":
            devs_by_type[dtype(r["device_id"])].add(r["device_id"])
    devs_by_type = {k: v for k, v in devs_by_type.items()}
    sets = offline_sets(devs_by_type)

    scenarios = []
    stop_flags = []
    for D in OUTAGE_LENGTHS:
        for sname, members in sets.items():
            for t0 in STARTS:
                t1 = t0 + D
                if t1 > RUN_S:
                    continue
                per_dev = [device_backlog(d, t0, t1, mons, recalls, hbatch) for d in members]
                tot_frames = sum(x["buffered_frames"] for x in per_dev)
                tot_tokens = sum(x["cold_rebuild_tokens"] for x in per_dev)
                # upload per device (parallel uplinks); report both link tiers
                R_by_tier = {}
                for tier, mbps in UPLINK.items():
                    # upload seconds = bytes / (bytes/s); add one RTT for the exchange
                    ups = [x["upload_bytes"] / uplink_bps(mbps) + RTT_MS / 1000.0 for x in per_dev]
                    max_up = max(ups) if ups else 0.0
                    gpu = tot_tokens / T_PEAK      # shared GPU, serial across offline devices
                    R_par = max(max_up, gpu)
                    R_ser = max_up + gpu
                    cnt, fit = in_window_decisions(recs_idx, t1, R_par)
                    cnt_s, fit_s = in_window_decisions(recs_idx, t1, R_ser)
                    R_by_tier[tier] = {
                        "uplink_mbps": mbps,
                        "max_device_upload_s": round(max_up, 4),
                        "gpu_rebuild_s": round(gpu, 4),
                        "R_pipelined_s": round(R_par, 4),
                        "R_serial_s": round(R_ser, 4),
                        "verdict_pipelined": verdict(R_par),
                        "verdict_serial": verdict(R_ser),
                        "in_window_decisions_pipelined": cnt,
                        "headroom_ceiling_pipelined": cnt,
                        "headroom_fit_pipelined": fit,
                        "in_window_decisions_serial": cnt_s,
                        "headroom_fit_serial": fit_s,
                    }
                    # STOP gate: headroom cannot exceed in-window decisions; R cannot be negative
                    for ty in cnt:
                        if fit[ty] > cnt[ty] or R_par < 0:
                            stop_flags.append(f"{D}s/{sname}/t{t0}/{tier}: fit>count or R<0")
                scenarios.append({
                    "outage_s": D, "offline_set": sname, "members": members,
                    "start_s": t0, "reconnect_s": t1,
                    "backlog": {"buffered_frames": tot_frames, "cold_rebuild_tokens": tot_tokens,
                                "upload_tokens_D2law": EPG_TEXT + EPG_PER_FRAME * tot_frames,
                                "per_device": per_dev},
                    "by_link_tier": R_by_tier,
                })

    # positive control: zero-length outage -> empty backlog, R 0, headroom 0
    pc = device_backlog(sorted(devs_by_type["dashcam"])[0], 400.0, 400.0, mons, recalls, hbatch)
    pc_ok = (pc["buffered_frames"] == 0 and pc["upload_bytes"] == 0.0)

    result = {
        "_what": "StudyOUTAGE-HEADROOM (PRELIMINARY): reconnect-burst recovery-window headroom.",
        "_prereg": "reports/study_outage_headroom.md",
        "trace_digest": dig, "digest_match": dig == COMMITTED_DIGEST,
        "constants": {"T_peak_tok_s": T_PEAK, "rtt_ms": RTT_MS, "net_one_way_s": NET_S,
                      "uplink_tiers_mbps": UPLINK, "bytes_per_frame": BYTES_PER_FRAME,
                      "question_text_bytes": QUESTION_TEXT_B, "deadlines_s": DEADLINE_S,
                      "epg_text_tokens": EPG_TEXT, "epg_tok_per_frame": EPG_PER_FRAME},
        "device_composition": {k: sorted(v) for k, v in devs_by_type.items()},
        "offline_sets": sets,
        "positive_control_D0": {"ok": pc_ok, "backlog": pc},
        "stop_flags": stop_flags,
        "n_scenarios": len(scenarios),
        "scenarios": scenarios,
    }
    result["_provenance"] = stamp(script="outage_headroom.py", model="qwen3vl32b",
                                  device="jetson_orin", n=len(scenarios), seed=4, args=TRACE_ARGS)
    out_json = ROOT / "reports/figures/outage_headroom_results.json"
    out_json.write_text(json.dumps(result, indent=1, default=float))
    print("wrote", out_json)
    print("digest match:", result["digest_match"], "| positive control D0 ok:", pc_ok,
          "| stop_flags:", len(stop_flags))
    return result


if __name__ == "__main__":
    run()
