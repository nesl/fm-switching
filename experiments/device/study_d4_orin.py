#!/usr/bin/env python3
"""
StudyD4-orin — fill the missing N=3 on-device cost + cost of a cheap motion signal.

Jetson Orin only. Same stack as StudyD8: llama.cpp c0fd786, Qwen3VL-4B-Instruct-F16
(sha256 verified), MAXN mode 0, GPU pinned 1.3005 GHz (verified + logged per request),
cache_prompt=FALSE (cold), greedy max 512, seed 0.

Inputs are DEV-RECENT frames from identical_input_manifest.json (sha256 re-verified).
N=3 = each question's N=9 frames at positions 1/5/9 (time order). These are NOT Nexar
frames and NOT the bytes the H100 used; per-frame ~332 tok ≈ Nexar SMALL ~336 tok.

Part A  isolated latency: N=3×50, N=1×20, N=9×20 (calibration vs StudyD8), one at a
        time, first-after-load discarded. TTFT + total p50/p90/p99 + rail energy/req.
Part B  sustained N=3 @2 s (or ceil(p99) if N=3 total p99 > 2 s), 30 min, skip-not-queue,
        + 10 min loaded-idle baseline. completed/missed/staleness/drift/power/energy/temp.
Part C  motion-feature cost: committed experiments/dashcam/d2_flow.py (Farneback, 17
        features), UNMODIFIED, CPU-only, server stopped, 50 windows of 9 manifest frames.
        time/window p50/p90 + CPU-rail power + one new-frame (single-pair) update cost.
        NOTE: d2_flow's working resolution is 384×216 (task said 768×432; honoring
        "do not change the features", measured at the code's native resolution).

Energy: tegrastats 100 ms, per-request trapezoid of total board power (3 INA3221 rails,
no VDD_IN on this Orin). Outputs under results/device/study_d4_orin/.
"""
import argparse, base64, hashlib, json, math, re, statistics as st, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import experiments.device.dev_inputs as dev
import experiments.device.dev_fast_latency as dfl
import experiments.device.study_dev_one as sdo
from experiments.lib._provenance import stamp

OUTDIR = dfl.OUTDIR / "study_d4_orin"
MANIFEST = dfl.OUTDIR / "identical_input_manifest.json"
FRAMES = dfl.FRAMES
PINNED_HZ = sdo.PINNED_HZ
GEN = dfl.GGUF["4bi_f16"][3]            # greedy, max_tokens=512, seed=0
STOP_TJ = 90.0
SETTLE = 0.15
ISO_GAP = 1.0                          # inter-request gap for the ISOLATED Part-A sets
D8_REF = {1: 0.513, 9: 3.843}          # StudyD8 arm TTFT p50 references


def pct(xs, q):
    xs = sorted(v for v in xs if v is not None)
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    i = q / 100 * (len(xs) - 1)
    lo = int(i); hi = min(lo + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (i - lo), 4)


def recent_tj(sampler, n=30):
    rows = sampler.snapshot()[-n:]
    tjs = [r["tj"] for r in rows if r.get("tj")]
    return max(tjs) if tjs else None


# ── frame selection ──────────────────────────────────────────────────────────
def picks9(qid):
    return sdo.picks_for_n(qid, 9)

def picks_n3(qid):
    p = picks9(qid)
    return [p[0], p[4], p[8]]           # positions 1,5,9 (1-indexed), already time-ordered

def picks_for(qid, N):
    if N == 1:
        return sdo.picks_for_n(qid, 1)
    if N == 3:
        return picks_n3(qid)
    if N == 9:
        return picks9(qid)
    raise ValueError(N)


# ── input sha256 verification vs manifest ────────────────────────────────────
def verify_inputs():
    man = json.load(open(MANIFEST))
    # map manifest frames by (qid,N) -> {t: sha256}
    idx = {}
    for e in man["entries"]:
        idx[(e["question_id"], e["N"])] = {f["t"]: f["sha256"] for f in e["frames"]}
    recs = dfl.load_sample_recs()
    ok = 0; checked = 0; bad = []
    for rec in recs:
        qid = rec["question_id"]
        n9 = idx.get((qid, 9), {})
        n1 = idx.get((qid, 1), {})
        for N, src in ((1, n1), (3, n9), (9, n9)):      # N=3 frames are a subset of N=9
            for t in picks_for(qid, N):
                checked += 1
                h = hashlib.sha256((FRAMES / qid / f"{t}.png").read_bytes()).hexdigest()
                if src.get(t) == h:
                    ok += 1
                else:
                    bad.append({"qid": qid, "N": N, "t": t})
    return {"checked": checked, "ok": ok, "n_bad": len(bad), "bad": bad[:10]}


# ── one request (explicit picks; cold; clock logged) ─────────────────────────
def run_req(rec, picks, cache_prompt=False):
    qid = rec["question_id"]
    items = [(t, base64.b64encode((FRAMES / qid / f"{t}.png").read_bytes()).decode()) for t in picks]
    content = dev.build_chat_content(rec, items)
    payload = {"model": "m", "messages": [{"role": "user", "content": content}],
               "stream": True, "stream_options": {"include_usage": True}, **GEN}
    if cache_prompt is not None:
        payload["cache_prompt"] = cache_prompt
    req = urllib.request.Request(f"{dfl.BASE}/v1/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    clk0 = dfl.gpu_freq()
    toks = []; wall_start = time.time(); t0 = time.perf_counter(); ttft = None; timings = None
    resp = urllib.request.urlopen(req)
    for raw in resp:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data: "):
            continue
        d = line[6:]
        if d == "[DONE]":
            break
        o = json.loads(d)
        if o.get("timings"):
            timings = o["timings"]
        ch = o.get("choices") or [{}]
        delta = ch[0].get("delta", {}) if ch else {}
        now = time.perf_counter()
        for lab, key in (("reason", "reasoning_content"), ("answer", "content")):
            if delta.get(key):
                if ttft is None:
                    ttft = now - t0
                toks.append((lab, delta[key]))
    total = time.perf_counter() - t0
    wall_end = time.time()
    clk1 = dfl.gpu_freq()
    ans = "".join(t for l, t in toks if l == "answer")
    rea = "".join(t for l, t in toks if l == "reason")
    m = re.search(r"\b([A-E])\b", ans) or re.search(r"\b([A-E])\b", rea[-50:] if rea else "")
    pred = m.group(1) if m else None
    tim = timings or {}
    return {
        "question_id": qid, "n_frames": len(picks), "cache_prompt": cache_prompt,
        "input_tokens": tim.get("prompt_n"), "prefill_ms": tim.get("prompt_ms"),
        "cached_n": tim.get("cache_n"),
        "ttft_s": round(ttft, 4) if ttft else None,
        "total_latency_s": round(total, 4),
        "n_gen": tim.get("predicted_n"),
        "pred": pred, "correct_letter": rec.get("correct_letter"),
        "correct": (pred == rec.get("correct_letter")) if pred else False,
        "gpu_clock_before": clk0, "gpu_clock_after": clk1,
        "clock_ok": (clk0 == PINNED_HZ and clk1 == PINNED_HZ),
        "wall_start": wall_start, "wall_end": wall_end,
    }


# ── Part A: isolated latency ─────────────────────────────────────────────────
def latency_stats(rows, Nlabel):
    ttfts = [r["ttft_s"] for r in rows]
    lats = [r["total_latency_s"] for r in rows]
    ej = [r["energy"]["energy_j"] for r in rows if r.get("energy")]
    rail = {k: [r["energy"][k] for r in rows if r.get("energy") and r["energy"].get(k) is not None]
            for k in ("gpu_j", "cpu_j", "sys_j")}
    toks = [r["input_tokens"] for r in rows if r["input_tokens"] is not None]
    cached = [r["cached_n"] for r in rows]
    by_q = {}
    for r in rows:
        by_q.setdefault(r["question_id"], []).append(r["pred"])
    rep = {k: v for k, v in by_q.items() if len(v) >= 2}
    match = (sum(1 for v in rep.values() if len(set(v)) == 1) / len(rep)) if rep else None
    return {
        "N": Nlabel, "n": len(rows),
        "input_tokens": {"p50": int(st.median(toks)) if toks else None,
                         "min": min(toks) if toks else None, "max": max(toks) if toks else None},
        "ttft_s": {"p50": pct(ttfts, 50), "p90": pct(ttfts, 90), "p99": pct(ttfts, 99)},
        "total_latency_s": {"p50": pct(lats, 50), "p90": pct(lats, 90), "p99": pct(lats, 99),
                            "max": round(max(lats), 4) if lats else None},
        "energy_j": {"p50": pct(ej, 50), "p90": pct(ej, 90)},
        "rail_energy_j_p50": {k: pct(v, 50) for k, v in rail.items()},
        "cached_n_min": min(cached) if cached else None, "cached_n_max": max(cached) if cached else None,
        "greedy_match_rate": match, "n_repeated_q": len(rep),
        "clock_bad_rows": sum(0 if r["clock_ok"] else 1 for r in rows),
        "accuracy_indicative": round(sum(1 for r in rows if r["correct"]) / len(rows), 4) if rows else None,
    }


def phase_A(recs, sampler, counts=(50, 20, 20)):
    n3, n1, n9 = counts
    out = {}
    fout = open(OUTDIR / "partA_isolated.jsonl", "w")

    def iso_set(N, count, start=0):
        rows = []
        for i in range(count):
            rec = recs[start + i]
            r = run_req(rec, picks_for(rec["question_id"], N))
            r["part"] = "A"; r["N"] = N
            time.sleep(SETTLE)
            r["energy"] = dfl.integrate(sampler.snapshot(), r["wall_start"], r["wall_end"])
            rows.append(r); fout.write(json.dumps(r) + "\n"); fout.flush()
            time.sleep(ISO_GAP)
        return rows

    # warm-up (first-after-load discarded): one per N, excluded
    warm = {N: run_req(recs[0], picks_for(recs[0]["question_id"], N)) for N in (9, 1, 3)}
    json.dump({str(N): {"ttft_s": w["ttft_s"], "total_latency_s": w["total_latency_s"],
                        "input_tokens": w["input_tokens"], "clock_ok": w["clock_ok"]}
               for N, w in warm.items()}, open(OUTDIR / "partA_warmup.json", "w"), indent=2)
    print(f"warmups (excluded): " + " ".join(
        f"N{N} ttft={w['ttft_s']}s in={w['input_tokens']}" for N, w in warm.items()), flush=True)
    time.sleep(3)

    print(f"Part A: N=3 × {n3} ...", flush=True)
    out["N3"] = latency_stats(iso_set(3, n3), 3)
    print(f"Part A: N=1 × {n1} ...", flush=True)
    out["N1"] = latency_stats(iso_set(1, n1), 1)
    print(f"Part A: N=9 × {n9} ...", flush=True)
    out["N9"] = latency_stats(iso_set(9, n9), 9)
    fout.close()
    for k in ("N1", "N3", "N9"):
        s = out[k]
        print(f"  {k}: tok~{s['input_tokens']['p50']} TTFT p50/p90/p99="
              f"{s['ttft_s']['p50']}/{s['ttft_s']['p90']}/{s['ttft_s']['p99']}s "
              f"total p50/p99={s['total_latency_s']['p50']}/{s['total_latency_s']['p99']}s "
              f"E p50={s['energy_j']['p50']}J match={s['greedy_match_rate']} cached_n≤{s['cached_n_max']}",
              flush=True)
    # calibration vs StudyD8
    for N, k in ((1, "N1"), (9, "N9")):
        r = out[k]["ttft_s"]["p50"] / D8_REF[N]
        out[k]["vs_studyd8_ttft_p50_ratio"] = round(r, 4)
        print(f"  calib N={N}: TTFT p50 {out[k]['ttft_s']['p50']}s vs StudyD8 {D8_REF[N]}s ratio={r:.3f}",
              flush=True)
    return out


# ── Part B: sustained N=3 (skip-not-queue) ───────────────────────────────────
def phase_B(recs, cadence, baseline_s=600, duration=1800):
    # baseline (loaded, idle)
    bgz = OUTDIR / "partB_baseline_tegrastats.jsonl.gz"
    bsamp = dfl.Sampler(bgz)
    print(f"Part B baseline: {baseline_s}s loaded-idle ...", flush=True)
    b0 = time.time(); time.sleep(baseline_s); b1 = time.time()
    baseline = dfl.idle_stats(bsamp.snapshot(), b0, b1)
    bsamp.stop()
    base_w = baseline["mean_total_w"] if baseline else None
    print(f"  baseline: {baseline}", flush=True)

    gz = OUTDIR / "partB_sustained_tegrastats.jsonl.gz"
    samp = dfl.Sampler(gz)
    fout = open(OUTDIR / "partB_sustained.jsonl", "w")
    rows = []; missed = 0; qi = 0; throttled = None
    t0 = time.time(); t_end = t0 + duration; scheduled = t0
    try:
        while scheduled < t_end:
            now = time.time()
            if now < scheduled:
                time.sleep(scheduled - now)
            tj = recent_tj(samp)
            if tj is not None and tj >= STOP_TJ:
                throttled = {"tj": tj, "after_requests": len(rows)}; break
            rec = recs[qi % len(recs)]; qi += 1
            r = run_req(rec, picks_n3(rec["question_id"]))
            r["part"] = "B"; r["N"] = 3; r["scheduled_time"] = scheduled
            r["staleness_s"] = round(r["wall_start"] - scheduled, 4)
            time.sleep(SETTLE)
            r["energy"] = dfl.integrate(samp.snapshot(), r["wall_start"], r["wall_end"])
            rows.append(r); fout.write(json.dumps(r) + "\n"); fout.flush()
            scheduled += cadence
            after = time.time()
            while scheduled < after and scheduled < t_end:
                missed += 1; scheduled += cadence
            if len(rows) % 50 == 0:
                e = r.get("energy") or {}
                print(f"  [B] {len(rows)} done {missed} missed {time.time()-t0:.0f}/{duration}s "
                      f"ttft={r['ttft_s']}s lat={r['total_latency_s']}s tj={tj}C", flush=True)
    finally:
        fout.close(); samp.stop()

    ttfts = [r["ttft_s"] for r in rows]
    lats = [r["total_latency_s"] for r in rows]
    stale = [r["staleness_s"] for r in rows]
    ej = [r["energy"]["energy_j"] for r in rows if r.get("energy")]
    pw = [r["energy"]["mean_w"] for r in rows if r.get("energy")]
    tj_all = [r["energy"]["tj_max"] for r in rows if r.get("energy") and r["energy"].get("tj_max")]
    cached = [r["cached_n"] for r in rows]
    def win(lo, hi):
        w = [r for r in rows if lo <= r["wall_start"] < hi]
        wt = [r["ttft_s"] for r in w]
        return {"n": len(w), "ttft_p50": pct(wt, 50)}
    by_q = {}
    for r in rows:
        by_q.setdefault(r["question_id"], []).append(r["pred"])
    rep = {k: v for k, v in by_q.items() if len(v) >= 2}
    match = (sum(1 for v in rep.values() if len(set(v)) == 1) / len(rep)) if rep else None
    mean_w = round(st.mean(pw), 3) if pw else None
    return {
        "cadence_s": cadence, "duration_s": duration,
        "baseline": baseline, "baseline_w": base_w,
        "requests_completed": len(rows), "missed_ticks": missed, "throttled": throttled,
        "input_tokens_median": int(st.median([r["input_tokens"] for r in rows if r["input_tokens"]])) if rows else None,
        "ttft_s": {"p50": pct(ttfts, 50), "p90": pct(ttfts, 90), "p99": pct(ttfts, 99)},
        "total_latency_s": {"p50": pct(lats, 50), "p90": pct(lats, 90), "p99": pct(lats, 99),
                            "max": round(max(lats), 4) if lats else None},
        "staleness_s": {"p50": pct(stale, 50), "p90": pct(stale, 90), "max": round(max(stale), 4) if stale else None},
        "energy_j_per_req": {"p50": pct(ej, 50), "p90": pct(ej, 90)},
        "mean_board_w": mean_w,
        "energy_per_hour_total_j": round(mean_w * 3600, 1) if mean_w else None,
        "energy_per_hour_above_baseline_j": round((mean_w - base_w) * 3600, 1) if (mean_w and base_w) else None,
        "tj_max_c": round(max(tj_all), 2) if tj_all else None,
        "drift_first10": win(t0, t0 + 600), "drift_last10": win(t_end - 600, t_end),
        "clock_bad_rows": sum(0 if r["clock_ok"] else 1 for r in rows),
        "greedy_match_rate": match, "n_repeated_q": len(rep),
        "cached_n_min": min(cached) if cached else None, "cached_n_max": max(cached) if cached else None,
        "accuracy_indicative": round(sum(1 for r in rows if r["correct"]) / len(rows), 4) if rows else None,
    }


# ── Part C: motion-feature cost (committed d2_flow, UNMODIFIED, CPU) ──────────
def phase_C(recs, n_windows=50):
    import experiments.dashcam.d2_flow as d2
    d2.FR = FRAMES                      # redirect input root to the manifest frames (features unchanged)
    import cv2
    cv2.setNumThreads(1)

    tgz = OUTDIR / "partC_tegrastats.jsonl.gz"
    samp = dfl.Sampler(tgz)
    time.sleep(2)
    c0 = time.time()
    per_window = []; feat_rows = []
    for rec in recs[:n_windows]:
        qid = rec["question_id"]; keys = picks9(qid)
        req = {"file_name": qid, "frame_keys": keys, "request_id": qid}
        t = time.perf_counter()
        rid, fv = d2.feats(req)         # the committed 9-frame / 8-pair / 17-feature computation
        dt = time.perf_counter() - t
        per_window.append(dt)
        feat_rows.append({"question_id": qid, "n_frames": len(keys), "time_s": round(dt, 5),
                          "resolution": [d2.W, d2.H], "features": fv})
    c1 = time.time()

    # marginal "one new-frame update" = single Farneback pair at the code's resolution (same params)
    q = recs[0]["question_id"]; ks = picks9(q)
    a = cv2.resize(cv2.imread(str(FRAMES / q / f"{ks[0]}.png"), cv2.IMREAD_GRAYSCALE), (d2.W, d2.H), interpolation=cv2.INTER_AREA)
    b = cv2.resize(cv2.imread(str(FRAMES / q / f"{ks[1]}.png"), cv2.IMREAD_GRAYSCALE), (d2.W, d2.H), interpolation=cv2.INTER_AREA)
    pair_t = []
    for _ in range(30):
        t = time.perf_counter()
        cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        pair_t.append(time.perf_counter() - t)
    c2 = time.time()
    samp.stop()

    rows = samp.snapshot()
    act = dfl.idle_stats(rows, c0, c1)          # power during the 50-window run
    json.dump(feat_rows, open(OUTDIR / "partC_features.json", "w"), indent=2)
    return {
        "n_windows": n_windows, "resolution": [d2.W, d2.H],
        "note": ("committed d2_flow.py UNMODIFIED; FR redirected to manifest frames; "
                 "working resolution 384x216 (task said 768x432 — features not changed); system cv2 " + cv2.__version__),
        "time_per_window_s": {"p50": pct(per_window, 50), "p90": pct(per_window, 90),
                              "p99": pct(per_window, 99), "min": round(min(per_window), 5),
                              "max": round(max(per_window), 5)},
        "pairs_per_window": 8,
        "new_frame_update_s": {"single_pair_p50": pct(pair_t, 50), "single_pair_p90": pct(pair_t, 90),
                               "window_over_8_p50": round(pct(per_window, 50) / 8, 5)},
        "cpu_rail_power_w": (act or {}).get("mean_cpu_w"),
        "board_power_w": (act or {}).get("mean_total_w"),
        "power_detail": act,
        "no_incremental_api": True,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--parts", default="ABC")
    a = ap.parse_args()
    OUTDIR.mkdir(parents=True, exist_ok=True)

    clk = dfl.gpu_freq()
    print(f"preflight clock={clk} pinned={PINNED_HZ} ok={clk == PINNED_HZ}", flush=True)
    if clk != PINNED_HZ:
        print("STOP: clock wrong", flush=True); return
    vin = verify_inputs()
    print(f"input sha256: ok={vin['ok']}/{vin['checked']} bad={vin['n_bad']}", flush=True)
    if vin["n_bad"]:
        print(f"STOP: input hash mismatch {vin['bad']}", flush=True); return

    recs = dfl.load_sample_recs()
    nwin, bsec, dur = 50, 600, 1800
    if a.smoke:
        nwin, bsec, dur = 3, 10, 25

    summary = {"config": {"model": "Qwen3VL-4B-Instruct-F16", "commit": "c0fd786",
                          "cache_prompt": False, "gen": GEN, "pinned_hz": PINNED_HZ,
                          "n3_from": "N=9 positions 1/5/9 (time order)",
                          "frames_note": "DEV-RECENT manifest frames; NOT Nexar, NOT H100 bytes; ~332 tok/frame ≈ Nexar SMALL ~336",
                          "input_sha256_verify": vin}, "parts": {}}

    server = None
    try:
        if "A" in a.parts or "B" in a.parts:
            print("launching server (4bi_f16)...", flush=True)
            server = dfl.launch_server("4bi_f16", dfl.SCRATCH / "study_d4_server.log")

        if "A" in a.parts:
            asamp = dfl.Sampler(OUTDIR / "partA_tegrastats.jsonl.gz")
            try:
                partA = phase_A(recs[:60], asamp, counts=(2, 2, 2) if a.smoke else (50, 20, 20))
            finally:
                asamp.stop()
            summary["parts"]["A"] = partA
            json.dump(summary, open(OUTDIR / "study_d4_summary.json", "w"), indent=2)

        if "B" in a.parts:
            # cadence from N=3 total-latency p99 (Part A); default 2 s
            p99 = summary.get("parts", {}).get("A", {}).get("N3", {}).get("total_latency_s", {}).get("p99")
            cadence = 2.0
            if p99 and p99 > 2.0:
                cadence = float(math.ceil(p99))
                print(f"N=3 total p99={p99}s > 2 s → cadence bumped to {cadence}s", flush=True)
            else:
                print(f"N=3 total p99={p99}s ≤ 2 s → cadence 2 s", flush=True)
            summary["parts"]["B"] = phase_B(recs, cadence, baseline_s=bsec, duration=dur)
            s = summary["parts"]["B"]
            print(f"Part B done: {s['requests_completed']} req {s['missed_ticks']} missed "
                  f"ttft p50/p99={s['ttft_s']['p50']}/{s['ttft_s']['p99']}s "
                  f"E/h_above={s['energy_per_hour_above_baseline_j']}J tj={s['tj_max_c']}C "
                  f"throttled={bool(s['throttled'])}", flush=True)
            json.dump(summary, open(OUTDIR / "study_d4_summary.json", "w"), indent=2)
    finally:
        if server is not None:
            dfl.stop_server(server)
            print("server stopped", flush=True)

    if "C" in a.parts:
        print(f"Part C: optical flow, {nwin} windows, server down ...", flush=True)
        summary["parts"]["C"] = phase_C(recs, n_windows=nwin)
        c = summary["parts"]["C"]
        print(f"Part C done: window p50/p90={c['time_per_window_s']['p50']}/{c['time_per_window_s']['p90']}s "
              f"new-frame single-pair p50={c['new_frame_update_s']['single_pair_p50']}s "
              f"cpu_rail={c['cpu_rail_power_w']}W", flush=True)

    summary["_provenance"] = stamp(script="study_d4_orin.py", model="4bi_f16",
                                   device="jetson_orin", n=len(recs), seed=0)
    json.dump(summary, open(OUTDIR / "study_d4_summary.json", "w"), indent=2)
    print("StudyD4-orin complete.", flush=True)


if __name__ == "__main__":
    main()
