#!/usr/bin/env python3
"""
StudyD8 — continuous local sensing cost on the Jetson AGX Orin.

Question: what does Qwen3VL-4B-Instruct cost when it runs as a *standing query*
(a sensor polled on a schedule, or flat-out) rather than as isolated requests?

Jetson Orin only. Same stack as StudyDevFast / StudyDevOne:
  llama.cpp c0fd786, Qwen3VL-4B-Instruct-F16 GGUF (+mmproj) with sha256 verified,
  server flags --jinja --reasoning-format deepseek -ngl 99 -fa on -c 16384,
  MAXN mode 0, GPU pinned 1.3005 GHz (verified + logged per request),
  greedy (temp 0) max 512, seed 0, cache_prompt=FALSE (cold every request).

Inputs are the EXACT N=1 and N=9 payloads recorded in
results/device/identical_input_manifest.json; their per-PNG sha256 is re-verified
against the cached frames before the run. The 120 questions are cycled in a fixed
order (seed 0).

Arms, run STRICTLY one at a time, nothing else on the Orin, one shared server:
  baseline : server loaded, no requests, 10 min  (the energy/power reference)
  A        : N=1, a new request every 1 s, 30 min
  B        : N=9, a new request every 5 s, 30 min
  C        : N=9, back-to-back (no idle), 60 min
Requests never overlap (single-threaded, synchronous). If a request is still
running when the next scheduled tick is due, that tick is SKIPPED and counted as
missed -- never queued.

Energy: tegrastats sampled every 100 ms continuously within each arm; per-request
energy is the trapezoidal integral of total board power over [wall_start,wall_end].
This Orin has NO VDD_IN rail; total board power = VDD_GPU_SOC+VDD_CPU_CV+VIN_SYS_5V0
(3 INA3221 rails, jtop "TOT"). Energy/hour above baseline uses the baseline arm's
mean board power.

Throttle: tj active trips are 75 / 95 C, GPU/CPU passive 99 C, critical 104.5 C.
If tj >= STOP_TJ (90 C) the current arm stops and the event is flagged.

Outputs (results/device/study_d8/):
  isolated_sanity.jsonl            isolated N=1/N=9 TTFT check vs 0.51 / 3.80 s
  arm_baseline_tegrastats.jsonl.gz
  arm_{A,B,C}.jsonl                per-request rows incl. per-request energy
  arm_{A,B,C}_tegrastats.jsonl.gz  100 ms raw power/temp trace per arm
  study_d8_summary.json            per-arm aggregates, sanity, provenance
  study_d8_progress.json           live progress (updated during the run)
"""
import argparse, gzip, hashlib, json, statistics as st, time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import experiments.device.dev_inputs as dev          # noqa: F401 (used via sdo)
import experiments.device.dev_fast_latency as dfl
import experiments.device.study_dev_one as sdo
from experiments.lib._provenance import stamp

OUTDIR = dfl.OUTDIR / "study_d8"
MANIFEST = dfl.OUTDIR / "identical_input_manifest.json"
PINNED_HZ = sdo.PINNED_HZ
GEN = dfl.GGUF["4bi_f16"][3]                 # greedy, max_tokens=512, seed=0
STOP_TJ = 90.0                               # stop an arm if junction temp reaches this
SETTLE = 0.15                                # let the bracketing tegrastats sample land

# prior isolated references (StudyDevOne / StudyDevFast corrected)
REF_TTFT = {1: 0.51, 9: 3.80}

# arm schedule: (name, N, interval_s or None for back-to-back, duration_s)
ARMS = [
    ("A", 1, 1.0, 30 * 60),
    ("B", 9, 5.0, 30 * 60),
    ("C", 9, None, 60 * 60),
]


def pct(xs, q):
    xs = sorted(v for v in xs if v is not None)
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    i = q / 100 * (len(xs) - 1)
    lo = int(i); hi = min(lo + 1, len(xs) - 1); frac = i - lo
    return round(xs[lo] + (xs[hi] - xs[lo]) * frac, 4)


def recent_tj(sampler, n=30):
    rows = sampler.snapshot()[-n:]
    tjs = [r["tj"] for r in rows if r.get("tj")]
    return max(tjs) if tjs else None


# ── input verification (byte-identical to the manifest) ──────────────────────
def verify_inputs():
    man = json.load(open(MANIFEST))
    idx = {(e["question_id"], e["N"]): [f["sha256"] for f in e["frames"]] for e in man["entries"]}
    recs = dfl.load_sample_recs()
    ok = 0; bad = []
    for rec in recs:
        qid = rec["question_id"]
        for N in (1, 9):
            picks = sdo.picks_for_n(qid, N)
            got = [hashlib.sha256((dfl.FRAMES / qid / f"{t}.png").read_bytes()).hexdigest() for t in picks]
            if idx.get((qid, N)) == got:
                ok += 1
            else:
                bad.append({"qid": qid, "N": N})
    return {"checked": 2 * len(recs), "ok": ok, "bad": bad[:10], "n_bad": len(bad)}


# ── one request (reuses StudyDevOne.run_one: N-selection, cold prefill, clock) ─
def do_request(rec, N, sampler, arm, scheduled):
    row = sdo.run_one(rec, N, GEN, cache_prompt=False)
    row["arm"] = arm
    row["scheduled_time"] = scheduled
    row["staleness_s"] = round(row["wall_start"] - scheduled, 4)
    time.sleep(SETTLE)
    row["energy"] = dfl.integrate(sampler.snapshot(), row["wall_start"], row["wall_end"])
    # keep only the fields StudyD8 reports (slim the row)
    keep = ("question_id", "N", "n_frames", "arm", "scheduled_time", "wall_start", "wall_end",
            "staleness_s", "input_tokens", "prefill_ms", "cached_n", "ttft_s", "total_latency_s",
            "n_gen", "pred", "correct_letter", "correct", "gpu_clock_before", "gpu_clock_after",
            "clock_ok", "energy")
    return {k: row.get(k) for k in keep}


# ── scheduled arm (A, B): fixed cadence, skip-if-busy ────────────────────────
def run_scheduled_arm(name, N, interval, duration, recs, sampler, fout, progress_cb):
    rows = []; missed = 0; qi = 0; throttled = None
    t0 = time.time(); t_end = t0 + duration
    scheduled = t0
    while scheduled < t_end:
        now = time.time()
        if now < scheduled:
            time.sleep(scheduled - now)
        tj = recent_tj(sampler)
        if tj is not None and tj >= STOP_TJ:
            throttled = {"tj": tj, "at": time.time(), "after_requests": len(rows)}
            break
        rec = recs[qi % len(recs)]; qi += 1
        r = do_request(rec, N, sampler, name, scheduled)
        rows.append(r)
        fout.write(json.dumps(r) + "\n"); fout.flush()
        # advance the schedule, skipping any ticks already past
        scheduled += interval
        after = time.time()
        while scheduled < after and scheduled < t_end:
            missed += 1
            scheduled += interval
        if len(rows) % 50 == 0:
            progress_cb(name, len(rows), missed, rows[-1], tj, t0, duration)
    return {"t_start": t0, "t_end": t_end, "duration_s": duration, "rows": rows,
            "missed": missed, "throttled": throttled}


# ── back-to-back arm (C): no idle, one after another ─────────────────────────
def run_backtoback_arm(name, N, duration, recs, sampler, fout, progress_cb):
    rows = []; qi = 0; throttled = None
    t0 = time.time(); t_end = t0 + duration
    prev_end = t0
    while time.time() < t_end:
        tj = recent_tj(sampler)
        if tj is not None and tj >= STOP_TJ:
            throttled = {"tj": tj, "at": time.time(), "after_requests": len(rows)}
            break
        rec = recs[qi % len(recs)]; qi += 1
        r = do_request(rec, N, sampler, name, prev_end)  # "due" the instant prev finished
        rows.append(r)
        fout.write(json.dumps(r) + "\n"); fout.flush()
        prev_end = r["wall_end"]
        if len(rows) % 50 == 0:
            progress_cb(name, len(rows), 0, rows[-1], tj, t0, duration)
    return {"t_start": t0, "t_end": t_end, "duration_s": duration, "rows": rows,
            "missed": 0, "throttled": throttled}


# ── per-arm aggregation ──────────────────────────────────────────────────────
def summarise_arm(name, N, res, baseline_w):
    rows = res["rows"]
    ttfts = [r["ttft_s"] for r in rows if r["ttft_s"] is not None]
    lats = [r["total_latency_s"] for r in rows]
    stale = [r["staleness_s"] for r in rows]
    ej = [r["energy"]["energy_j"] for r in rows if r.get("energy")]
    pw = [r["energy"]["mean_w"] for r in rows if r.get("energy")]
    cached = [r["cached_n"] for r in rows]
    toks = [r["input_tokens"] for r in rows if r["input_tokens"] is not None]
    tj_all = [r["energy"]["tj_max"] for r in rows if r.get("energy") and r["energy"].get("tj_max")]
    clock_bad = sum(0 if r["clock_ok"] else 1 for r in rows)

    # drift: first 10 min vs last 10 min (TTFT p50 and mean power)
    t0, t1 = res["t_start"], res["t_end"]
    def window(lo, hi):
        w = [r for r in rows if lo <= r["wall_start"] < hi]
        wt = [r["ttft_s"] for r in w if r["ttft_s"] is not None]
        wp = [r["energy"]["mean_w"] for r in w if r.get("energy")]
        return {"n": len(w), "ttft_p50": pct(wt, 50), "mean_w": round(st.mean(wp), 3) if wp else None}
    first10 = window(t0, t0 + 600)
    last10 = window(t1 - 600, t1)

    # greedy letter-match across repeated identical requests (per qid+N)
    by_q = {}
    for r in rows:
        by_q.setdefault((r["question_id"], r["N"]), []).append(r["pred"])
    repeated = {k: v for k, v in by_q.items() if len(v) >= 2}
    matched = sum(1 for v in repeated.values() if len(set(v)) == 1)
    match_rate = (matched / len(repeated)) if repeated else None

    # indicative accuracy over UNIQUE questions (first occurrence)
    seen = {}
    for r in rows:
        seen.setdefault(r["question_id"], r)
    uq = list(seen.values())
    acc_correct = sum(1 for r in uq if r["correct"])

    # energy per hour
    total_s = (rows[-1]["wall_end"] - rows[0]["wall_start"]) if rows else 0.0
    total_j = sum(ej)
    mean_board_w = round(st.mean(pw), 3) if pw else None
    e_per_hr_total = round(mean_board_w * 3600, 1) if mean_board_w else None
    e_per_hr_above = (round((mean_board_w - baseline_w) * 3600, 1)
                      if (mean_board_w and baseline_w) else None)

    return {
        "arm": name, "N": N, "cadence": ("every 1 s" if name == "A" else
                                         "every 5 s" if name == "B" else "back-to-back"),
        "duration_s": res["duration_s"],
        "requests_completed": len(rows), "missed_ticks": res["missed"],
        "throttled": res["throttled"],
        "input_tokens_median": int(st.median(toks)) if toks else None,
        "cached_n_min": min(cached) if cached else None,
        "cached_n_max": max(cached) if cached else None,
        "ttft_s": {"p50": pct(ttfts, 50), "p90": pct(ttfts, 90), "p99": pct(ttfts, 99),
                   "min": round(min(ttfts), 4) if ttfts else None,
                   "max": round(max(ttfts), 4) if ttfts else None},
        "total_latency_s": {"p50": pct(lats, 50), "p90": pct(lats, 90), "p99": pct(lats, 99),
                            "max": round(max(lats), 4) if lats else None},
        "staleness_s": {"p50": pct(stale, 50), "p90": pct(stale, 90),
                        "max": round(max(stale), 4) if stale else None},
        "energy_j_per_req": {"p50": pct(ej, 50), "p90": pct(ej, 90),
                             "max": round(max(ej), 2) if ej else None},
        "mean_board_w": mean_board_w,
        "energy_per_hour_total_j": e_per_hr_total,
        "energy_per_hour_above_baseline_j": e_per_hr_above,
        "tj_max_c": round(max(tj_all), 2) if tj_all else None,
        "clock_bad_rows": clock_bad,
        "drift_first10": first10, "drift_last10": last10,
        "greedy_match_rate": match_rate, "n_repeated_q": len(repeated),
        "accuracy_indicative": {"unique_q": len(uq), "correct": acc_correct,
                                "acc": round(acc_correct / len(uq), 4) if uq else None},
    }


def _progress_file(d):
    json.dump(d, open(OUTDIR / "study_d8_progress.json", "w"), indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="tiny timings to validate the harness end-to-end")
    a = ap.parse_args()
    OUTDIR.mkdir(parents=True, exist_ok=True)

    arms = ARMS
    baseline_s = 10 * 60
    iso_counts = (10, 10)
    if a.smoke:
        arms = [("A", 1, 1.0, 20), ("B", 9, 5.0, 20), ("C", 9, None, 20)]
        baseline_s = 15
        iso_counts = (2, 2)

    # preflight: clock + input sha256 + model already verified in shell
    clk = dfl.gpu_freq()
    print(f"preflight gpu clock={clk} pinned={PINNED_HZ} ok={clk == PINNED_HZ}", flush=True)
    if clk != PINNED_HZ:
        print("STOP: clock wrong", flush=True); return
    vin = verify_inputs()
    print(f"input sha256 verify: ok={vin['ok']}/{vin['checked']} bad={vin['n_bad']}", flush=True)
    if vin["n_bad"]:
        print(f"STOP: input hash mismatch {vin['bad']}", flush=True); return

    recs = dfl.load_sample_recs()
    srv_log = dfl.SCRATCH / "study_d8_server.log"
    print("launching server (4bi_f16)...", flush=True)
    server = dfl.launch_server("4bi_f16", srv_log)
    summary = {"arms": {}, "sanity": {}, "config": {
        "model": "Qwen3VL-4B-Instruct-F16", "commit": "c0fd786", "cache_prompt": False,
        "gen": GEN, "pinned_hz": PINNED_HZ, "stop_tj_c": STOP_TJ,
        "thermal_trips_c": {"tj_active": [75, 95], "gpu_cpu_passive": 99, "critical": 104.5},
        "input_sha256_verify": vin,
        "arms": [{"name": n, "N": N, "interval_s": iv, "duration_s": d} for n, N, iv, d in arms],
        "baseline_s": baseline_s}}

    def progress_cb(name, done, missed, last, tj, t0, dur):
        el = time.time() - t0
        e = last.get("energy") or {}
        msg = (f"  [{name}] {done} done, {missed} missed, {el:.0f}/{dur}s | "
               f"ttft={last['ttft_s']}s lat={last['total_latency_s']}s "
               f"E={e.get('energy_j')}J tj={tj}C clk_ok={last['clock_ok']}")
        print(msg, flush=True)
        _progress_file({"arm": name, "elapsed_s": round(el), "duration_s": dur,
                        "completed": done, "missed": missed, "last": last,
                        "updated": time.time()})

    try:
        # warm-up (excluded): load CUDA graphs / allocate for both N
        for N in (1, 9):
            w = sdo.run_one(recs[0], N, GEN, cache_prompt=False)
            print(f"warmup N={N} (excluded): ttft={w['ttft_s']}s in={w['input_tokens']} "
                  f"clk_ok={w['clock_ok']}", flush=True)
        time.sleep(3)

        # ── isolated sanity: isolated N=1 / N=9 TTFT vs prior refs ──
        iso_path = OUTDIR / "isolated_sanity.jsonl"
        fiso = open(iso_path, "w")
        iso = {1: [], 9: []}
        for N, cnt in zip((1, 9), iso_counts):
            for i in range(cnt):
                r = sdo.run_one(recs[i], N, GEN, cache_prompt=False)
                r["arm"] = f"isolated_n{N}"
                fiso.write(json.dumps({k: r.get(k) for k in
                           ("question_id", "N", "arm", "input_tokens", "cached_n", "ttft_s",
                            "total_latency_s", "pred", "correct", "clock_ok")}) + "\n")
                fiso.flush()
                iso[N].append(r["ttft_s"])
                time.sleep(3)  # idle gap: keep isolated (not sustained)
        fiso.close()
        for N in (1, 9):
            med = st.median(iso[N]); ref = REF_TTFT[N]
            summary["sanity"][f"isolated_n{N}_ttft"] = {
                "median_s": round(med, 4), "ref_s": ref, "ratio": round(med / ref, 4),
                "ttfts": [round(x, 4) for x in iso[N]]}
            print(f"isolated N={N}: TTFT median={med:.3f}s vs ref {ref}s ratio={med/ref:.3f}",
                  flush=True)
        _progress_file({"phase": "isolated done", "sanity": summary["sanity"]})

        # ── baseline arm: server loaded, no requests ──
        print(f"=== baseline: {baseline_s}s loaded-idle ===", flush=True)
        bgz = OUTDIR / "arm_baseline_tegrastats.jsonl.gz"
        bsamp = dfl.Sampler(bgz)
        b0 = time.time(); time.sleep(baseline_s); b1 = time.time()
        baseline = dfl.idle_stats(bsamp.snapshot(), b0, b1)
        bsamp.stop()
        baseline_w = baseline["mean_total_w"] if baseline else None
        summary["arms"]["baseline"] = {"window_s": baseline_s, "idle": baseline,
                                       "mean_board_w": baseline_w}
        print(f"baseline loaded-idle: {baseline}", flush=True)

        # ── sustained arms A, B, C ──
        for name, N, interval, duration in arms:
            print(f"=== arm {name}: N={N} "
                  f"{'back-to-back' if interval is None else f'every {interval}s'} "
                  f"{duration}s ===", flush=True)
            gz = OUTDIR / f"arm_{name}_tegrastats.jsonl.gz"
            samp = dfl.Sampler(gz)
            fout = open(OUTDIR / f"arm_{name}.jsonl", "w")
            try:
                if interval is None:
                    res = run_backtoback_arm(name, N, duration, recs, samp, fout, progress_cb)
                else:
                    res = run_scheduled_arm(name, N, interval, duration, recs, samp, fout,
                                            progress_cb)
            finally:
                fout.close(); samp.stop()
            summary["arms"][name] = summarise_arm(name, N, res, baseline_w)
            s = summary["arms"][name]
            print(f"arm {name} done: {s['requests_completed']} req, {s['missed_ticks']} missed, "
                  f"ttft p50/p90/p99={s['ttft_s']['p50']}/{s['ttft_s']['p90']}/{s['ttft_s']['p99']}s "
                  f"E/hr_total={s['energy_per_hour_total_j']}J tj_max={s['tj_max_c']}C "
                  f"throttled={bool(s['throttled'])}", flush=True)
            summary["_provenance"] = stamp(script="study_d8_sustained.py", model="4bi_f16",
                                           device="jetson_orin", n=len(recs), seed=0)
            json.dump(summary, open(OUTDIR / "study_d8_summary.json", "w"), indent=2)
            if s["throttled"]:
                print(f"THROTTLE on arm {name}: {s['throttled']} -- stopping arm, continuing",
                      flush=True)
    finally:
        dfl.stop_server(server)
        print("server stopped", flush=True)
    print("StudyD8 run complete.", flush=True)


if __name__ == "__main__":
    main()
