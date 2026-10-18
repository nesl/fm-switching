#!/usr/bin/env python3
"""
Device latency runner for DEV-RECENT S-EMBER inputs on llama.cpp (Jetson Orin).

Two sub-commands:
  frames  : for each video in the 120-question sample, download it (HF token from
            hf-token.txt), extract the per-question DEV-RECENT frames (uniform over
            [qt-120,qt], 1 fps source, resized 560x560), cache them, DELETE the video.
            Never more than 2 videos on disk. Frames cached so model phases don't re-fetch.
  run     : run one model phase against an already-running llama-server (--model-tag),
            logging per request: qid, model, format, N, input tokens, prefill, TTFT,
            per-token (ts,label), think tokens, </think> closed, budget hit, total latency,
            predicted answer, correctness, peak mem (tegrastats), GPU temp/clock.

Compact per-request -> results/device/latency_sember_<model>_<format>.jsonl
Per-token arrays    -> gzip at results/device/tokens_<model>_<format>.jsonl.gz
"""
import argparse, base64, glob, gzip, io, json, os, re, subprocess, sys, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import experiments.device.dev_inputs as dev

ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE = ROOT / "results/device/latency_sember_sample.json"
MCQ = ROOT / "results/sember/study_h/data/sember_mcq.jsonl"
SCRATCH = Path("/tmp/claude-1000/-home-nesl-fm-switching/9d6d4966-962f-4dd3-bb26-a868cceb7ec7/scratchpad")
FRAMES = SCRATCH / "devrecent_frames"      # qid/<t>.png  (560x560)
VIDTMP = SCRATCH / "video_tmp"
OUTDIR = ROOT / "results/device"
BASE = "http://127.0.0.1:8080"
TOKEN = (ROOT / "hf-token.txt").read_text().strip()

import imageio_ffmpeg
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def load_sample_recs():
    ids = json.load(open(SAMPLE))["question_ids"]
    mcq = {json.loads(l)["question_id"]: json.loads(l) for l in open(MCQ)}
    return [mcq[q] for q in ids]


# ── frames phase ────────────────────────────────────────────────────────────
def extract_frames_for_video(video_path, recs_for_video):
    """For each question on this video, extract its DEV-RECENT frames to FRAMES/<qid>/."""
    from PIL import Image
    for rec in recs_for_video:
        qid = rec["question_id"]; qt = float(rec["question_time"])
        outd = FRAMES / qid
        n = dev.choose_n(rec)
        want = dev.frame_times(qt, n)                 # desired integer-second timestamps
        if outd.exists() and len(list(outd.glob("*.png"))) >= 1 and (outd / "ts.json").exists():
            continue
        outd.mkdir(parents=True, exist_ok=True)
        lo = max(0.0, qt - dev.WINDOW_S)
        # one ffmpeg pass: 1 fps frames over [lo, qt], scaled to 560x560, numbered
        tmp = VIDTMP / f"grab_{qid}"
        tmp.mkdir(parents=True, exist_ok=True)
        dur = max(1.0, qt - lo)
        cmd = [FFMPEG, "-nostdin", "-ss", str(lo), "-t", str(dur + 0.5), "-i", str(video_path),
               "-vf", "fps=1,scale=560:560:flags=lanczos", "-start_number", str(int(round(lo))),
               "-frames:v", str(int(dur) + 2), str(tmp / "f_%d.png"), "-y"]
        subprocess.run(cmd, capture_output=True)
        avail = sorted(int(m.group(1)) for p in tmp.glob("f_*.png")
                       if (m := re.match(r"f_(\d+)\.png", p.name)))
        picks = dev.nearest_available(want, avail) if avail else []
        saved = []
        for t in picks:
            src = tmp / f"f_{t}.png"
            if src.exists():
                src.replace(outd / f"{t}.png"); saved.append(t)
        json.dump({"timestamps": saved, "n": len(saved), "qt": qt},
                  open(outd / "ts.json", "w"))
        for p in tmp.glob("*.png"):
            p.unlink()
        tmp.rmdir()


def phase_frames():
    recs = load_sample_recs()
    by_vid = {}
    for r in recs:
        by_vid.setdefault(r["video_id"], []).append(r)
    FRAMES.mkdir(parents=True, exist_ok=True); VIDTMP.mkdir(parents=True, exist_ok=True)
    from huggingface_hub import hf_hub_download
    vids = list(by_vid)
    print(f"frames phase: {len(recs)} questions over {len(vids)} videos", flush=True)
    for i, vid in enumerate(vids, 1):
        done = all((FRAMES / r["question_id"] / "ts.json").exists() for r in by_vid[vid])
        if done:
            print(f"[{i}/{len(vids)}] {vid[:28]} cached", flush=True); continue
        t0 = time.time()
        try:
            vp = hf_hub_download("facebook/S-EMBER", f"videos/{vid}.mp4", repo_type="dataset",
                                 local_dir=str(VIDTMP), token=TOKEN)
        except Exception as e:
            print(f"[{i}/{len(vids)}] {vid[:28]} FETCH-ERR {type(e).__name__}: {str(e)[:80]}", flush=True)
            continue
        extract_frames_for_video(vp, by_vid[vid])
        try:
            os.remove(vp)
        except OSError:
            pass
        # clean any nested hf dirs to keep <=2 videos on disk
        for stray in VIDTMP.rglob("*.mp4"):
            stray.unlink()
        print(f"[{i}/{len(vids)}] {vid[:28]} {len(by_vid[vid])}q  {time.time()-t0:.0f}s  "
              f"disk_free={os.statvfs('/').f_bavail*os.statvfs('/').f_frsize/1e9:.0f}GB", flush=True)
    print("frames phase done", flush=True)


# ── run phase (against live server) ──────────────────────────────────────────
def tegrastats_sample():
    try:
        p = subprocess.Popen([FFMPEG_TEGRA := "tegrastats", "--interval", "200"],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    except FileNotFoundError:
        return None, None, None
    ram = temp = freq = None
    try:
        for _ in range(10):
            line = p.stdout.readline()
            if not line:
                break
            mr = re.search(r"RAM (\d+)/\d+MB", line); mt = re.search(r"tj@([\d.]+)C", line)
            mf = re.search(r"GR3D_FREQ \d+%@?(\d+)?", line)
            if mr: ram = int(mr.group(1))
            if mt: temp = float(mt.group(1))
            if ram and temp:
                break
    finally:
        p.terminate()
    try:
        freq = int(open("/sys/devices/platform/bus@0/17000000.gpu/devfreq/17000000.gpu/cur_freq").read())
    except Exception:
        pass
    return ram, temp, freq


def load_frames(qid):
    outd = FRAMES / qid
    meta = json.load(open(outd / "ts.json"))
    items = []
    for t in meta["timestamps"]:
        b = base64.b64encode((outd / f"{t}.png").read_bytes()).decode()
        items.append((t, b))
    return items, meta


def run_one(rec, gen_params, model_tag, fmt):
    qid = rec["question_id"]
    items, meta = load_frames(qid)
    content = dev.build_chat_content(rec, items)
    payload = {"model": "m", "messages": [{"role": "user", "content": content}],
               "stream": True, "stream_options": {"include_usage": True}, **gen_params}
    req = urllib.request.Request(f"{BASE}/v1/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    ram0, temp0, freq0 = tegrastats_sample()
    toks = []  # (t, label, text)
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
    ram1, temp1, freq1 = tegrastats_sample()
    ans_text = "".join(t for _, l, t in toks if l == "answer")
    reason_text = "".join(t for _, l, t in toks if l == "reason")
    n_ans = sum(1 for _, l, _ in toks if l == "answer")
    n_rea = sum(1 for _, l, _ in toks if l == "reason")
    pred = None
    m = re.search(r"\b([A-E])\b", ans_text) or re.search(r"\b([A-E])\b", reason_text[-50:] if reason_text else "")
    if m:
        pred = m.group(1)
    tim = timings or {}
    maxtok = gen_params.get("max_tokens", 0)
    n_gen = (tim.get("predicted_n") or (n_rea + n_ans))
    rec_row = {
        "question_id": qid, "model": model_tag, "format": fmt,
        "n_frames": meta["n"], "input_tokens": tim.get("prompt_n"),
        "prefill_ms": tim.get("prompt_ms"),
        "ttft_s": round(ttft, 3) if ttft else None,
        "n_think_tokens": n_rea, "n_answer_tokens": n_ans, "n_gen": n_gen,
        "think_closed": (n_ans > 0),
        "budget_hit": bool(n_gen >= maxtok - 5) if maxtok else False,
        "total_latency_s": round(total, 3),
        "decode_tps": round((n_rea + n_ans - 1) / (total - (ttft or 0)), 2) if (n_rea + n_ans) > 1 and total > (ttft or 0) else None,
        "pred": pred, "correct_letter": rec.get("correct_letter"),
        "correct": (pred == rec.get("correct_letter")) if pred else False,
        "evidence_covered": None,  # filled from sample rec below
        "question_category": rec.get("question_category"),
        "peak_ram_mb": max(x for x in [ram0, ram1] if x) if (ram0 or ram1) else None,
        "tj_c_before": temp0, "tj_c_after": temp1,
        "gpu_freq_before": freq0, "gpu_freq_after": freq1,
    }
    tok_row = {"question_id": qid, "model": model_tag, "format": fmt, "tokens": toks}
    return rec_row, tok_row


MODELS = {
    # tag: (format, gen_params)
    "4bt_f16": ("F16", dict(temperature=1.0, top_p=0.95, top_k=20, presence_penalty=0.0,
                            repeat_penalty=1.0, max_tokens=16384, seed=0)),
    "4bi_f16": ("F16", dict(temperature=0.0, max_tokens=512, seed=0)),
    "4bt_q8":  ("Q8_0", dict(temperature=1.0, top_p=0.95, top_k=20, presence_penalty=0.0,
                            repeat_penalty=1.0, max_tokens=16384, seed=0)),
    "8bt_f16": ("F16", dict(temperature=1.0, top_p=0.95, top_k=20, presence_penalty=0.0,
                            repeat_penalty=1.0, max_tokens=16384, seed=0)),
    "8bi_f16": ("F16", dict(temperature=0.0, max_tokens=512, seed=0)),
}


def phase_run(model_tag, limit=None):
    fmt, gen = MODELS[model_tag]
    recs = load_sample_recs()
    # evidence_covered from the sample's RECENT records
    recent = {json.loads(l)["question_id"]: json.loads(l)
              for l in open(ROOT / "results/sember/study_o/study_o_q4_trials_fa2.jsonl")
              if json.loads(l)["state_arm"] == "RECENT"}
    if limit:
        recs = recs[:limit]
    out_jsonl = OUTDIR / f"latency_sember_{model_tag}_{fmt}.jsonl"
    tok_gz = OUTDIR / f"tokens_{model_tag}_{fmt}.jsonl.gz"
    done = set()
    if out_jsonl.exists():
        done = {json.loads(l)["question_id"] for l in open(out_jsonl)}
    fout = open(out_jsonl, "a")
    ftok = gzip.open(tok_gz, "at")
    for i, rec in enumerate(recs, 1):
        qid = rec["question_id"]
        if qid in done:
            continue
        if not (FRAMES / qid / "ts.json").exists():
            print(f"[{i}/{len(recs)}] {qid[:12]} NO FRAMES, skip", flush=True); continue
        row, tok = run_one(rec, gen, model_tag, fmt)
        row["evidence_covered"] = bool(recent.get(qid, {}).get("evidence_covered"))
        fout.write(json.dumps(row) + "\n"); fout.flush()
        ftok.write(json.dumps(tok) + "\n"); ftok.flush()
        if i % 10 == 0 or i == len(recs):
            print(f"[{i}/{len(recs)}] {qid[:12]} N={row['n_frames']} in={row['input_tokens']} "
                  f"prefill={row['prefill_ms']}ms ttft={row['ttft_s']}s dtps={row['decode_tps']} "
                  f"ngen={row['n_gen']} lat={row['total_latency_s']}s pred={row['pred']} "
                  f"ok={row['correct']} tj={row['tj_c_after']}", flush=True)
    fout.close(); ftok.close()
    print(f"phase {model_tag} done -> {out_jsonl}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["frames", "4bt_f16", "4bi_f16", "4bt_q8", "8bt_f16", "8bi_f16"])
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    if a.phase == "frames":
        phase_frames()
    else:
        phase_run(a.phase, a.limit)


if __name__ == "__main__":
    main()
