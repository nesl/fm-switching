#!/usr/bin/env python3
"""
StudyDevOne — one-frame (N=1) device measurement + identical-input manifest + reachability.

Jetson Orin only. Records the N=1 cold latency/energy and the EXACT image payloads
(N=37/18/9/1) so the H100 can run byte-identical inputs. Reuses the StudyDevFast
harness (server flags, energy sampler, frame selection).

Subcommands:
  manifest : Part 1 — write results/device/identical_input_manifest.json (CPU only).
  run      : Part 2 — control gate (10 x N=9 within 10% of StudyDevFast 3.80 s) then
             N=1 cold (cache_prompt=false) x 120 with per-request energy. Needs a server.
  reach    : Part 3 — reachability to the H100 host (CPU only, no installs).

Caching: Part 2 N=1 uses cache_prompt=FALSE (cold prefill, each input distinct). The
control uses StudyDevFast conditions (cache_prompt default) to reproduce 3.80 s.
"""
import argparse, base64, gzip, hashlib, json, re, shutil, socket, subprocess, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import experiments.device.dev_inputs as dev
import experiments.device.dev_fast_latency as dfl
from experiments.lib._provenance import stamp

ROOT = dfl.ROOT
FRAMES = dfl.FRAMES
OUTDIR = dfl.OUTDIR
BASE = dfl.BASE
PINNED_HZ = 1300500000
STUDYDEVFAST_N9_TTFT = 3.80       # corrected control target
H100_HOST = "sn4622120321"
NS_MANIFEST = [37, 18, 9, 1]


# ── frame selection (identical to StudyDevFast for 37/18/9; N=1 = frame at/nearest-before qt) ──
def picks_for_n(qid, N):
    meta = json.load(open(FRAMES / qid / "ts.json"))
    avail = sorted(meta["timestamps"])
    qt = float(meta["qt"])
    if N == 1:
        at_or_before = [t for t in avail if t <= round(qt)]
        return [max(at_or_before)] if at_or_before else [min(avail)]
    if N >= len(avail):
        return avail
    want = dev.frame_times(qt, N)
    return dev.nearest_available(want, avail)


def frame_items(qid, picks):
    """[(t, png_bytes, b64)] in time order from cached 560x560 PNGs."""
    out = []
    for t in picks:
        b = (FRAMES / qid / f"{t}.png").read_bytes()
        out.append((t, b, base64.b64encode(b).decode()))
    return out


# ── Part 1: manifest ─────────────────────────────────────────────────────────
def build_manifest():
    from PIL import Image
    import io
    recs = dfl.load_sample_recs()
    entries = []
    for rec in recs:
        qid = rec["question_id"]
        for N in NS_MANIFEST:
            picks = picks_for_n(qid, N)
            frames = []
            for t in picks:
                b = (FRAMES / qid / f"{t}.png").read_bytes()
                im = Image.open(io.BytesIO(b))
                frames.append({
                    "t": t, "marker": f"[t={t}s]",
                    "sha256": hashlib.sha256(b).hexdigest(),
                    "width": im.width, "height": im.height, "bytes": len(b),
                })
            entries.append({
                "question_id": qid, "N": N, "n_frames": len(frames),
                "question_time": float(rec["question_time"]),
                "video_id": rec.get("video_id"),
                "frames": frames,
                "question_text_sha256": hashlib.sha256(dev.question_text(rec).encode()).hexdigest(),
            })
    manifest = {
        "_about": ("Exact DEV-RECENT image payloads per (question_id, N) for StudyDevOne / "
                   "StudyDeviceLatency / StudyDevFast. Frames are 560x560 PNGs (PIL/ffmpeg "
                   "lanczos), each preceded by its [t=Xs] marker, then question_text(rec). "
                   "N=37/18/9 = StudyDevFast selection; N=1 = frame at/nearest-before qt. "
                   "sha256 is of the raw PNG bytes sent (base64) to llama.cpp. PNG bytes live "
                   "in Orin scratch (devrecent_frames); use these hashes to verify identical inputs."),
        "per_frame_image_tokens": dev.PER_FRAME_IMAGE_TOKENS,
        "resolution": list(dev.RESOLUTION), "window_s": dev.WINDOW_S,
        "n_questions": len(recs), "ns": NS_MANIFEST,
        "entries": entries,
        "_provenance": stamp(script="study_dev_one.py", model="qwenvl4b", device="jetson_orin",
                             n=len(recs)),
    }
    out = OUTDIR / "identical_input_manifest.json"
    json.dump(manifest, open(out, "w"))
    # quick report
    import statistics as st
    for N in NS_MANIFEST:
        nf = [e["n_frames"] for e in entries if e["N"] == N]
        print(f"N={N}: {len(nf)} questions, n_frames median={st.median(nf)} min={min(nf)} max={max(nf)}")
    print(f"wrote {out}  ({out.stat().st_size/1e6:.2f} MB)")


# ── Part 2: one request (cold-capable, gpu-clock logged) ─────────────────────
def run_one(rec, N, gen, cache_prompt):
    qid = rec["question_id"]
    items = frame_items(qid, picks_for_n(qid, N))
    content = dev.build_chat_content(rec, [(t, b64) for t, _b, b64 in items])
    payload = {"model": "m", "messages": [{"role": "user", "content": content}],
               "stream": True, "stream_options": {"include_usage": True}, **gen}
    if cache_prompt is not None:
        payload["cache_prompt"] = cache_prompt
    req = urllib.request.Request(f"{BASE}/v1/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    clk0 = dfl.gpu_freq()
    toks = []
    wall_start = time.time(); t0 = time.perf_counter(); ttft = None; timings = None
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
                toks.append((round(now - t0, 4), lab, delta[key]))
    total = time.perf_counter() - t0
    wall_end = time.time()
    clk1 = dfl.gpu_freq()
    ans_text = "".join(t for _, l, t in toks if l == "answer")
    reason_text = "".join(t for _, l, t in toks if l == "reason")
    n_ans = sum(1 for _, l, _ in toks if l == "answer")
    n_rea = sum(1 for _, l, _ in toks if l == "reason")
    pred = None
    m = re.search(r"\b([A-E])\b", ans_text) or re.search(r"\b([A-E])\b", reason_text[-50:] if reason_text else "")
    if m:
        pred = m.group(1)
    tim = timings or {}
    row = {
        "question_id": qid, "N": N, "n_frames": len(items),
        "cache_prompt": cache_prompt,
        "input_tokens": tim.get("prompt_n"), "prefill_ms": tim.get("prompt_ms"),
        "cached_n": tim.get("cache_n"),
        "ttft_s": round(ttft, 3) if ttft else None,
        "n_gen": tim.get("predicted_n") or (n_rea + n_ans),
        "total_latency_s": round(total, 3),
        "pred": pred, "correct_letter": rec.get("correct_letter"),
        "correct": (pred == rec.get("correct_letter")) if pred else False,
        "question_category": rec.get("question_category"),
        "gpu_clock_before": clk0, "gpu_clock_after": clk1,
        "clock_ok": (clk0 == PINNED_HZ and clk1 == PINNED_HZ),
        "wall_start": wall_start, "wall_end": wall_end,
    }
    return row


def phase_run(limit=None):
    gen_i = dfl.GGUF["4bi_f16"][3]           # greedy, max 512, seed 0
    recs = dfl.load_sample_recs()
    if limit:
        recs = recs[:limit]
    clk = dfl.gpu_freq()
    print(f"preflight gpu clock = {clk} (pinned {PINNED_HZ}) ok={clk==PINNED_HZ}", flush=True)
    if clk != PINNED_HZ:
        print("STOP: clock wrong", flush=True); return
    srv_log = dfl.SCRATCH / "dev_one_server.log"
    print("launching server (4bi_f16)...", flush=True)
    server = dfl.launch_server("4bi_f16", srv_log)
    tegra = OUTDIR / "dev_one_tegrastats.jsonl.gz"
    sampler = dfl.Sampler(tegra)
    try:
        _phase_body(recs, gen_i, sampler)
    finally:
        sampler.stop()
        dfl.stop_server(server)
        print("server stopped", flush=True)


def _phase_body(recs, gen_i, sampler):
    import statistics as st

    # warm-up (logged separately, excluded)
    warm = run_one(recs[0], 1, gen_i, cache_prompt=False)
    json.dump(warm, open(OUTDIR / "dev_one_warmup.json", "w"), indent=2)
    print(f"warmup (excluded): N=1 ttft={warm['ttft_s']}s lat={warm['total_latency_s']}s "
          f"prompt_n={warm['input_tokens']} clock_ok={warm['clock_ok']}", flush=True)
    time.sleep(3)

    # CONTROL gate: 10 x N=9 at StudyDevFast conditions (cache_prompt default)
    ctrl_path = OUTDIR / "dev_one_control_n9.jsonl"
    fc = open(ctrl_path, "w")
    ttfts = []
    for i, rec in enumerate(recs[:10], 1):
        r = run_one(rec, 9, gen_i, cache_prompt=None)
        r["energy"] = None
        fc.write(json.dumps(r) + "\n"); fc.flush()
        ttfts.append(r["ttft_s"])
        print(f"  ctrl[{i}/10] N=9 ttft={r['ttft_s']}s in={r['input_tokens']} clock_ok={r['clock_ok']}", flush=True)
    fc.close()
    import statistics as st
    ctrl_med = st.median(ttfts)
    ratio = ctrl_med / STUDYDEVFAST_N9_TTFT
    passed = abs(ratio - 1) <= 0.10
    print(f"CONTROL: N=9 TTFT median={ctrl_med:.3f}s vs {STUDYDEVFAST_N9_TTFT}s "
          f"ratio={ratio:.3f} within10%={passed}", flush=True)
    json.dump({"ttft_median_s": ctrl_med, "target_s": STUDYDEVFAST_N9_TTFT, "ratio": ratio,
               "within_10pct": passed, "ttfts": ttfts},
              open(OUTDIR / "dev_one_control_result.json", "w"), indent=2)
    if not passed:
        sampler.stop()
        print("STOP: control failed", flush=True); return

    # idle baseline (loaded, idle) before the N=1 sweep
    idle_start = time.time(); time.sleep(60); idle_end = time.time()
    idle = dfl.idle_stats(sampler.snapshot(), idle_start, idle_end)
    print(f"idle baseline: {idle}", flush=True)

    # N=1 COLD sweep
    out = OUTDIR / "dev_one_n1.jsonl"
    done = {json.loads(l)["question_id"] for l in open(out)} if out.exists() else set()
    fout = open(out, "a")
    for i, rec in enumerate(recs, 1):
        if rec["question_id"] in done:
            continue
        r = run_one(rec, 1, gen_i, cache_prompt=False)
        time.sleep(0.15)
        r["energy"] = dfl.integrate(sampler.snapshot(), r["wall_start"], r["wall_end"])
        fout.write(json.dumps(r) + "\n"); fout.flush()
        if i % 20 == 0 or i == len(recs):
            e = r["energy"] or {}
            print(f"  [{i}/{len(recs)}] N=1 in={r['input_tokens']} ttft={r['ttft_s']}s "
                  f"lat={r['total_latency_s']}s E={e.get('energy_j')}J clock_ok={r['clock_ok']}", flush=True)
    fout.close()
    sampler.stop()
    json.dump({"idle": idle, "idle_start": idle_start, "idle_end": idle_end,
               "control": {"ttft_median_s": ctrl_med, "ratio": ratio, "passed": passed},
               "_provenance": stamp(script="study_dev_one.py", model="4bi_f16",
                                    device="jetson_orin", n=len(recs), seed=0)},
              open(OUTDIR / "dev_one_summary.json", "w"), indent=2)
    print("phase_run done", flush=True)


# ── Part 3: reachability ─────────────────────────────────────────────────────
def phase_reach():
    res = {"host": H100_HOST, "checks": {}}
    # DNS / /etc/hosts resolution
    try:
        res["checks"]["resolve"] = {"ok": True, "ip": socket.gethostbyname(H100_HOST)}
    except Exception as e:
        res["checks"]["resolve"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    # ping (3 packets)
    try:
        p = subprocess.run(["ping", "-c", "3", "-W", "2", H100_HOST],
                           capture_output=True, text=True, timeout=20)
        res["checks"]["ping"] = {"rc": p.returncode, "stdout": p.stdout[-800:], "stderr": p.stderr[-300:]}
    except Exception as e:
        res["checks"]["ping"] = {"error": f"{type(e).__name__}: {e}"}
    # route
    try:
        p = subprocess.run(["ip", "route", "get", res["checks"]["resolve"].get("ip", H100_HOST)],
                           capture_output=True, text=True, timeout=10)
        res["checks"]["route"] = p.stdout.strip() or p.stderr.strip()
    except Exception as e:
        res["checks"]["route"] = f"{type(e).__name__}: {e}"
    # TCP probe to common ports (SSH, vLLM)
    res["checks"]["tcp"] = {}
    ip = res["checks"]["resolve"].get("ip", H100_HOST)
    for port in (22, 8000, 8080):
        try:
            s = socket.create_connection((ip, port), timeout=3); s.close()
            res["checks"]["tcp"][port] = "open"
        except Exception as e:
            res["checks"]["tcp"][port] = f"{type(e).__name__}"
    # already-installed throughput tools (do not install)
    res["checks"]["tools_present"] = {t: bool(shutil.which(t)) for t in ("iperf3", "iperf", "nc", "ssh", "scp", "rsync", "curl")}
    # ssh config hosts (does an alias exist?)
    sc = Path.home() / ".ssh/config"
    if sc.exists():
        hits = [l.strip() for l in sc.read_text().splitlines()
                if l.strip().lower().startswith("host ") and (H100_HOST in l or "sn4622" in l)]
        res["checks"]["ssh_config_alias"] = hits or "no matching Host alias"
    else:
        res["checks"]["ssh_config_alias"] = "no ~/.ssh/config"
    res["_provenance"] = stamp(script="study_dev_one.py", model="n/a", device="jetson_orin")
    json.dump(res, open(OUTDIR / "dev_one_reachability.json", "w"), indent=2)
    print(json.dumps(res["checks"], indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["manifest", "run", "reach"])
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    if a.phase == "manifest":
        build_manifest()
    elif a.phase == "run":
        phase_run(a.limit)
    elif a.phase == "reach":
        phase_reach()


if __name__ == "__main__":
    main()
