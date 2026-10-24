#!/usr/bin/env python3
"""
StudyDevFast — fast-path (shortened DEV-RECENT) latency + ENERGY on the Jetson Orin.

Question: can the device answer a DEV-RECENT S-EMBER question within a few seconds
when the recent-frame input is shortened (N frames), and what is the energy cost per
configuration?

Design (pre-registered in research/EXPERIMENTS.md, StudyDevFast):
  - Same stack/harness as StudyDeviceLatency-sember: llama.cpp c0fd786, F16 GGUFs
    (sha256 recorded in results/device/model_hashes.txt), same server flags
    (--jinja --reasoning-format deepseek -ngl 99 -fa on -c 16384), same 120-question
    sample, prompt caching ON (default).
  - Sweep: N in {37 (control), 18, 9} x models {4B-Instruct greedy max512,
    4B-Thinking model-card sampling seed0 max16384} = 6 cells x 120 q.
  - N=18/9 frames are the nearest-available subset of the CACHED N=37 DEV-RECENT
    frames (same window; no video re-fetch, so the device is inference-only during
    energy measurement). A documented approximation of frame_times(qt,N) snapped to
    the cached ~1 fps grid.
  - Cells run STRICTLY one at a time (one server, one request at a time, tegrastats
    the only other process). MAXN mode 0, GPU pinned 1.3005 GHz.

Energy: tegrastats sampled every 100 ms for the whole cell; per-request energy is the
trapezoidal integral of total board power over [wall_start, wall_end]. This Orin has
NO VDD_IN rail; total board power = VDD_GPU_SOC + VDD_CPU_CV + VIN_SYS_5V0 (the three
INA3221 channels; jtop "TOT" convention), reported with per-rail breakdown. A 60 s
loaded-idle baseline (server up, model loaded, no request) is measured before each cell.

Outputs (results/device/):
  devfast_<tag>_n<N>.jsonl         per-request rows incl. per-request energy (J)
  devfast_tegrastats_<tag>_n<N>.jsonl.gz   100 ms raw power trace for the cell
  devfast_summary.json             per-cell aggregates + idle baselines + provenance
"""
import argparse, base64, gzip, json, os, re, signal, subprocess, sys, threading, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import experiments.device.dev_inputs as dev
from experiments.lib._provenance import stamp

ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE = ROOT / "results/device/latency_sember_sample.json"
MCQ = ROOT / "results/sember/study_h/data/sember_mcq.jsonl"
SCRATCH = Path("/tmp/claude-1000/-home-nesl-fm-switching/9d6d4966-962f-4dd3-bb26-a868cceb7ec7/scratchpad")
FRAMES = SCRATCH / "devrecent_frames"
OUTDIR = ROOT / "results/device"
BASE = "http://127.0.0.1:8080"
LLAMA = Path.home() / "llama.cpp/build/bin/llama-server"
GPU_FREQ_PATH = "/sys/devices/platform/bus@0/17000000.gpu/devfreq/17000000.gpu/cur_freq"

HOME = Path.home()
GGUF = {
    # tag: (weights, mmproj, format, gen_params)
    "4bi_f16": (HOME / "models/qwen3vl4b-instruct-gguf/Qwen3VL-4B-Instruct-F16.gguf",
                HOME / "models/qwen3vl4b-instruct-gguf/mmproj-Qwen3VL-4B-Instruct-F16.gguf",
                "F16", dict(temperature=0.0, max_tokens=512, seed=0)),
    "4bt_f16": (HOME / "models/qwen3vl4b-thinking-gguf/Qwen3VL-4B-Thinking-F16.gguf",
                HOME / "models/qwen3vl4b-thinking-gguf/mmproj-Qwen3VL-4B-Thinking-F16.gguf",
                "F16", dict(temperature=1.0, top_p=0.95, top_k=20, presence_penalty=0.0,
                            repeat_penalty=1.0, max_tokens=16384, seed=0)),
}
NS = [37, 18, 9]
SERVER_FLAGS = ["-ngl", "99", "-fa", "on", "-c", "16384", "--jinja",
                "--reasoning-format", "deepseek", "--host", "127.0.0.1", "--port", "8080"]

RE_GPU = re.compile(r"VDD_GPU_SOC (\d+)mW")
RE_CPU = re.compile(r"VDD_CPU_CV (\d+)mW")
RE_SYS = re.compile(r"VIN_SYS_5V0 (\d+)mW")
RE_TJ = re.compile(r"tj@([\d.]+)C")
RE_GR3D = re.compile(r"GR3D_FREQ (\d+)%")
RE_RAM = re.compile(r"RAM (\d+)/\d+MB")


def gpu_freq():
    try:
        return int(open(GPU_FREQ_PATH).read())
    except Exception:
        return None


def load_sample_recs():
    ids = json.load(open(SAMPLE))["question_ids"]
    mcq = {json.loads(l)["question_id"]: json.loads(l) for l in open(MCQ)}
    return [mcq[q] for q in ids]


# ── tegrastats continuous sampler ────────────────────────────────────────────
class Sampler:
    def __init__(self, gz_path):
        self.rows = []
        self.lock = threading.Lock()
        self.gz = gzip.open(gz_path, "wt")
        self.proc = subprocess.Popen(["tegrastats", "--interval", "100"],
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self.stop_flag = False
        self.th = threading.Thread(target=self._read, daemon=True)
        self.th.start()

    def _read(self):
        for line in self.proc.stdout:
            wall = time.time()
            g = RE_GPU.search(line); c = RE_CPU.search(line); s = RE_SYS.search(line)
            if not (g and c and s):
                continue
            gm, cm, sm = int(g.group(1)), int(c.group(1)), int(s.group(1))
            tj = RE_TJ.search(line); gr = RE_GR3D.search(line); rm = RE_RAM.search(line)
            row = {"t": wall, "gpu_mw": gm, "cpu_mw": cm, "sys_mw": sm, "tot_mw": gm + cm + sm,
                   "tj": float(tj.group(1)) if tj else None,
                   "gr3d": int(gr.group(1)) if gr else None,
                   "ram_mb": int(rm.group(1)) if rm else None}
            with self.lock:
                self.rows.append(row)
            self.gz.write(json.dumps(row) + "\n")
            if self.stop_flag:
                break

    def snapshot(self):
        with self.lock:
            return list(self.rows)

    def stop(self):
        self.stop_flag = True
        try:
            self.proc.terminate()
        except Exception:
            pass
        self.th.join(timeout=3)
        try:
            self.gz.close()
        except Exception:
            pass


def integrate(rows, s, e):
    """Trapezoidal integral of power (mW) over [s, e] in wall-clock seconds -> Joules.
    Uses samples inside the window plus the bracketing samples at each edge (clamped)."""
    rows = [r for r in rows if r["t"] is not None]
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: r["t"])
    inside = [r for r in rows if s <= r["t"] <= e]
    # bracketing samples for edge accuracy
    before = [r for r in rows if r["t"] < s]
    after = [r for r in rows if r["t"] > e]
    seq = []
    if before:
        b = before[-1].copy(); b = {**b, "t": s}; seq.append(b)  # clamp to s at last-known power
    seq += inside
    if after:
        a = after[0].copy(); a = {**a, "t": e}; seq.append(a)     # clamp to e
    if len(seq) < 2:
        # fall back to nearest-sample mean power x duration
        p = inside[0]["tot_mw"] if inside else (before[-1]["tot_mw"] if before else
                                                after[0]["tot_mw"] if after else 0)
        dur = max(0.0, e - s)
        return {"energy_j": p * dur / 1000.0, "gpu_j": None, "cpu_j": None, "sys_j": None,
                "mean_w": p / 1000.0, "n_samples": len(inside), "peak_ram_mb": None, "tj_max": None}
    out = {"energy_j": 0.0, "gpu_j": 0.0, "cpu_j": 0.0, "sys_j": 0.0}
    for a, b in zip(seq[:-1], seq[1:]):
        dt = b["t"] - a["t"]
        if dt <= 0:
            continue
        out["energy_j"] += (a["tot_mw"] + b["tot_mw"]) / 2 * dt / 1000.0
        out["gpu_j"] += (a["gpu_mw"] + b["gpu_mw"]) / 2 * dt / 1000.0
        out["cpu_j"] += (a["cpu_mw"] + b["cpu_mw"]) / 2 * dt / 1000.0
        out["sys_j"] += (a["sys_mw"] + b["sys_mw"]) / 2 * dt / 1000.0
    dur = max(1e-9, e - s)
    out["mean_w"] = out["energy_j"] / dur
    out["n_samples"] = len(inside)
    out["peak_ram_mb"] = max((r["ram_mb"] for r in inside if r["ram_mb"]), default=None)
    out["tj_max"] = max((r["tj"] for r in inside if r["tj"]), default=None)
    out = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in out.items()}
    return out


def idle_stats(rows, s, e):
    inside = [r for r in rows if r["t"] is not None and s <= r["t"] <= e]
    if not inside:
        return None
    tot = [r["tot_mw"] for r in inside]
    return {
        "window_s": round(e - s, 2), "n_samples": len(inside),
        "mean_total_w": round(sum(tot) / len(tot) / 1000.0, 4),
        "mean_gpu_w": round(sum(r["gpu_mw"] for r in inside) / len(inside) / 1000.0, 4),
        "mean_cpu_w": round(sum(r["cpu_mw"] for r in inside) / len(inside) / 1000.0, 4),
        "mean_sys_w": round(sum(r["sys_mw"] for r in inside) / len(inside) / 1000.0, 4),
        "min_total_w": round(min(tot) / 1000.0, 4), "max_total_w": round(max(tot) / 1000.0, 4),
        "tj_mean": round(sum(r["tj"] for r in inside if r["tj"]) / len(inside), 2),
    }


# ── server ───────────────────────────────────────────────────────────────────
def launch_server(model_tag, log_path):
    weights, mmproj, fmt, gen = GGUF[model_tag]
    cmd = [str(LLAMA), "-m", str(weights), "--mmproj", str(mmproj), *SERVER_FLAGS]
    log = open(log_path, "w")
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                            preexec_fn=os.setsid, stdin=subprocess.DEVNULL)
    # wait for health
    t0 = time.time()
    while time.time() - t0 < 300:
        try:
            r = urllib.request.urlopen(f"{BASE}/health", timeout=2)
            if r.status == 200:
                print(f"  server up ({model_tag}) in {time.time()-t0:.0f}s", flush=True)
                return proc
        except Exception:
            pass
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early (rc={proc.returncode}); see {log_path}")
        time.sleep(2)
    raise RuntimeError("server health timeout")


def stop_server(proc):
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        pass
    try:
        proc.wait(timeout=30)
    except Exception:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            pass
    time.sleep(2)


# ── frame selection (N subset of cached N=37) ────────────────────────────────
def select_frames(qid, N):
    meta = json.load(open(FRAMES / qid / "ts.json"))
    avail = sorted(meta["timestamps"])
    qt = float(meta["qt"])
    if N >= len(avail):
        picks = avail                       # control: use all cached frames (== prior run)
    else:
        want = dev.frame_times(qt, N)
        picks = dev.nearest_available(want, avail)
    items = []
    for t in picks:
        b = base64.b64encode((FRAMES / qid / f"{t}.png").read_bytes()).decode()
        items.append((t, b))
    return items, len(picks)


# ── one request ──────────────────────────────────────────────────────────────
def run_one(rec, gen, model_tag, fmt, N):
    qid = rec["question_id"]
    items, nf = select_frames(qid, N)
    content = dev.build_chat_content(rec, items)
    payload = {"model": "m", "messages": [{"role": "user", "content": content}],
               "stream": True, "stream_options": {"include_usage": True}, **gen}
    req = urllib.request.Request(f"{BASE}/v1/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    toks = []
    wall_start = time.time()
    t0 = time.perf_counter(); ttft = None; timings = None
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
    ans_text = "".join(t for _, l, t in toks if l == "answer")
    reason_text = "".join(t for _, l, t in toks if l == "reason")
    n_ans = sum(1 for _, l, _ in toks if l == "answer")
    n_rea = sum(1 for _, l, _ in toks if l == "reason")
    pred = None
    m = re.search(r"\b([A-E])\b", ans_text) or re.search(r"\b([A-E])\b", reason_text[-50:] if reason_text else "")
    if m:
        pred = m.group(1)
    tim = timings or {}
    maxtok = gen.get("max_tokens", 0)
    n_gen = tim.get("predicted_n") or (n_rea + n_ans)
    row = {
        "question_id": qid, "model": model_tag, "format": fmt, "N": N, "n_frames": nf,
        "input_tokens": tim.get("prompt_n"), "prefill_ms": tim.get("prompt_ms"),
        "ttft_s": round(ttft, 3) if ttft else None,
        "n_think_tokens": n_rea, "n_answer_tokens": n_ans, "n_gen": n_gen,
        "think_closed": (n_ans > 0),
        "budget_hit": bool(n_gen >= maxtok - 5) if maxtok else False,
        "total_latency_s": round(total, 3),
        "decode_tps": round((n_rea + n_ans - 1) / (total - (ttft or 0)), 2)
                      if (n_rea + n_ans) > 1 and total > (ttft or 0) else None,
        "pred": pred, "correct_letter": rec.get("correct_letter"),
        "correct": (pred == rec.get("correct_letter")) if pred else False,
        "question_category": rec.get("question_category"),
        "wall_start": wall_start, "wall_end": wall_end,
    }
    tok_row = {"question_id": qid, "model": model_tag, "N": N, "tokens": toks}
    return row, tok_row


# ── cell ─────────────────────────────────────────────────────────────────────
def run_cell(model_tag, N, recs, recent_map, idle_s_cfg):
    fmt, gen = GGUF[model_tag][2], GGUF[model_tag][3]
    out_jsonl = OUTDIR / f"devfast_{model_tag}_n{N}.jsonl"
    tok_gz = OUTDIR / f"devfast_tokens_{model_tag}_n{N}.jsonl.gz"
    tegra_gz = OUTDIR / f"devfast_tegrastats_{model_tag}_n{N}.jsonl.gz"
    done = set()
    if out_jsonl.exists():
        done = {json.loads(l)["question_id"] for l in open(out_jsonl)}
    todo = [r for r in recs if r["question_id"] not in done]
    if not todo:
        print(f"cell {model_tag} N={N}: already complete ({len(done)})", flush=True)
        # recover idle from existing summary if present
        return None
    print(f"=== cell {model_tag} N={N}: {len(todo)} to run ({len(done)} done) ===", flush=True)
    sampler = Sampler(tegra_gz)
    # warmup (not logged): 1 request at this N
    try:
        run_one(todo[0], gen, model_tag, fmt, N)
        print("  warmup ok", flush=True)
    except Exception as e:
        print(f"  warmup err {e}", flush=True)
    time.sleep(3)  # settle: let the warmup tail clear before the idle baseline
    # idle baseline (loaded, idle)
    idle_start = time.time()
    time.sleep(idle_s_cfg)
    idle_end = time.time()
    idle = idle_stats(sampler.snapshot(), idle_start, idle_end)
    print(f"  idle baseline: {idle}", flush=True)
    fout = open(out_jsonl, "a")
    ftok = gzip.open(tok_gz, "at")
    for i, rec in enumerate(todo, 1):
        row, tok = run_one(rec, gen, model_tag, fmt, N)
        row["evidence_covered"] = bool(recent_map.get(rec["question_id"], {}).get("evidence_covered"))
        time.sleep(0.15)  # let the bracketing tegrastats sample land
        row["energy"] = integrate(sampler.snapshot(), row["wall_start"], row["wall_end"])
        fout.write(json.dumps(row) + "\n"); fout.flush()
        ftok.write(json.dumps(tok) + "\n"); ftok.flush()
        if i % 10 == 0 or i == len(todo):
            e = row["energy"] or {}
            print(f"  [{i}/{len(todo)}] {rec['question_id'][:12]} N={row['n_frames']} "
                  f"in={row['input_tokens']} ttft={row['ttft_s']}s lat={row['total_latency_s']}s "
                  f"ngen={row['n_gen']} E={e.get('energy_j')}J P={e.get('mean_w')}W "
                  f"ok={row['correct']} tj={e.get('tj_max')}", flush=True)
    fout.close(); ftok.close()
    sampler.stop()
    return {"idle": idle, "idle_start": idle_start, "idle_end": idle_end}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["4bi_f16", "4bt_f16"])
    ap.add_argument("--ns", nargs="+", type=int, default=NS)
    ap.add_argument("--limit", type=int, default=None, help="cap questions (smoke test)")
    ap.add_argument("--idle", type=float, default=60.0, help="idle-baseline seconds")
    a = ap.parse_args()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    recs = load_sample_recs()
    if a.limit:
        recs = recs[:a.limit]
    recent_map = {}
    po = ROOT / "results/sember/study_o/study_o_q4_trials_fa2.jsonl"
    if po.exists():
        for l in open(po):
            r = json.loads(l)
            if r.get("state_arm") == "RECENT":
                recent_map[r["question_id"]] = r

    summary_path = OUTDIR / "devfast_summary.json"
    summary = json.load(open(summary_path)) if summary_path.exists() else {"cells": {}}
    for model_tag in a.models:
        log_path = SCRATCH / f"devfast_server_{model_tag}.log"
        print(f"\n### launching server for {model_tag}", flush=True)
        proc = launch_server(model_tag, log_path)
        try:
            for N in a.ns:
                res = run_cell(model_tag, N, recs, recent_map, a.idle)
                key = f"{model_tag}_n{N}"
                if res:
                    summary["cells"][key] = res
                    summary["_provenance"] = stamp(script="dev_fast_latency.py",
                                                   model=model_tag, device="jetson_orin",
                                                   n=len(recs), seed=0, args=a)
                    json.dump(summary, open(summary_path, "w"), indent=2)
        finally:
            stop_server(proc)
            print(f"### server stopped for {model_tag}", flush=True)
    print("\nStudyDevFast run complete.", flush=True)


if __name__ == "__main__":
    main()
