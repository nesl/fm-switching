#!/usr/bin/env python3
"""Device-tier ACCURACY on S-EMBER with the device's own runtime and inputs.

The Orin measured latency for DEV-RECENT under llama.cpp; this measures accuracy
under the IDENTICAL runtime (llama.cpp c0fd786, same server flags, same GGUFs by
sha256) and the IDENTICAL input construction (experiments/device/dev_inputs.py),
on the same 845 Study O questions. The A6000 is used only because the Orin cannot
hold the videos; nothing about the inputs is A6000-specific.

Cells:
  C1 4B-Instruct x DEV-RECENT   greedy, max 512
  C2 4B-Instruct x DEV-RICH     greedy, max 512
  C3 4B-Thinking x DEV-RECENT   model-card VL sampling, max 16384
  C4 4B-Thinking x DEV-RICH     same as C3
"""
import argparse, json, os, re, signal, subprocess, sys, time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "experiments" / "lib"))
import dev_inputs as DI
from _provenance import stamp

GGUF = Path("/home/pragya/device_tier/gguf")
LLAMA_SERVER = Path("/home/pragya/device_tier/llama.cpp/build/bin/llama-server")
VIDEOS = ROOT / "results/sember/study_i/videos"
FRAME_CACHE = Path(os.environ.get("O_FRAME_CACHE",
                                  "/tmp/claude-1001/-home-pragya-Desktop-FM-switching/"
                                  "8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/oframes"))
POOL = ROOT / "results/sember/study_o/study_o_q4_trials_fa2.jsonl"
ORIN_SAMPLE = ROOT / "results/device/latency_sember_sample.json"
OUT_DIR = ROOT / "results/device"

MODELS = {
    "4B-I": dict(lm="Qwen3VL-4B-Instruct-F16.gguf",
                 mmproj="mmproj-Qwen3VL-4B-Instruct-F16.gguf",
                 lm_sha="4a6fb1ed053e162887bfc372bd7ffaaa9b8e4049ac6e9b9398ae7277162ec761",
                 mmproj_sha="256f3a43bd4205ffef48d6b92715e1e70b5b0e9aef06522584967513a9985331"),
    "4B-T": dict(lm="Qwen3VL-4B-Thinking-F16.gguf",
                 mmproj="mmproj-Qwen3VL-4B-Thinking-F16.gguf",
                 lm_sha="b0af534e2a0a90d53886c46129de279f45cdd82ca7e513141c9e3a4e14f36d93",
                 mmproj_sha="b8b81037542461bd874e66cfc2c72d3c7e50007cb4ed5b37257474e031b405c6"),
    "4B-T-Q8": dict(lm="Qwen3VL-4B-Thinking-Q8_0.gguf",
                    mmproj="mmproj-Qwen3VL-4B-Thinking-F16.gguf",
                    lm_sha="7c6f9a84ef6d4d62500f6a68a35df26e9abe31833bb6b9c812970593b09525cb",
                    mmproj_sha="b8b81037542461bd874e66cfc2c72d3c7e50007cb4ed5b37257474e031b405c6"),
}

# Orin's sampling for the Thinking runs was the model-card VL setting at temperature
# 1.0 (reports/device_latency_sember.md), not StudyO's 0.6 -- matching it keeps the
# accuracy and latency runs on the same distribution.
CELLS = {
    "C1": dict(model="4B-I", construction="RECENT",
               gen=dict(temperature=0.0, max_tokens=512)),
    "C2": dict(model="4B-I", construction="RICH",
               gen=dict(temperature=0.0, max_tokens=512)),
    "C3": dict(model="4B-T", construction="RECENT",
               gen=dict(temperature=1.0, top_p=0.95, top_k=20, presence_penalty=0.0,
                        repeat_penalty=1.0, max_tokens=16384)),
    "C4": dict(model="4B-T", construction="RICH",
               gen=dict(temperature=1.0, top_p=0.95, top_k=20, presence_penalty=0.0,
                        repeat_penalty=1.0, max_tokens=16384)),
    "C3q8": dict(model="4B-T-Q8", construction="RECENT",
                 gen=dict(temperature=1.0, top_p=0.95, top_k=20, presence_penalty=0.0,
                          repeat_penalty=1.0, max_tokens=16384)),
}

SERVER_SEED = 0
LETTER = re.compile(r"\b([A-E])\b")


# ---------------------------------------------------------------------------

def sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_models(key):
    """Refuse to run on weights that are not byte-identical to the Orin's."""
    spec = MODELS[key]
    for which in ("lm", "mmproj"):
        p = GGUF / spec[which]
        if not p.exists():
            raise SystemExit(f"FATAL: missing {p}")
        got = sha256(p)
        if got != spec[f"{which}_sha"]:
            raise SystemExit(f"FATAL: {p.name} sha256 {got} != Orin's {spec[f'{which}_sha']}")
        print(f"  {p.name}: sha256 OK", flush=True)
    return GGUF / spec["lm"], GGUF / spec["mmproj"]


def load_pool():
    """The 845 Study O questions, by question_id, with evidence intervals."""
    want = set()
    for line in open(POOL):
        want.add(json.loads(line)["question_id"])
    mcq = DI.load_mcq()
    have = {p.stem for p in VIDEOS.glob("*.mp4")}
    out = []
    for qid in sorted(want):
        r = mcq[qid]
        if r["video_id"] not in have:
            raise SystemExit(f"FATAL: video missing for {qid}")
        out.append(r)
    out.sort(key=lambda r: (r["video_id"], r["question_id"]))
    return out


def cached_frames(video_id):
    """[(t, path)] from the Study O 1 fps JPEG cache, timestamps as whole seconds.

    The cache stores floats (0.0, 1.0, ...). DEV-RECENT's contract is whole seconds
    and the Orin picked integer frame numbers, so a float here would render the
    marker as "[t=1.0s]" instead of "[t=1s]" -- +2 tokens per frame, which both
    breaks input identity with the Orin and overruns the 12,500 budget at N=37."""
    d = FRAME_CACHE / video_id
    idx = d / "index.json"
    if not idx.exists():
        raise SystemExit(f"FATAL: no frame cache for {video_id} at {d}")
    saved = json.load(open(idx))
    out, seen = [], set()
    for t, f in saved["frames"]:
        ti = int(round(float(t)))
        if ti not in seen:
            seen.add(ti)
            out.append((ti, d / f))
    return out


def covered(ts, rec):
    """study_o_q4.covered: any SAMPLED timestamp inside the evidence interval."""
    a, b = float(rec["answer_start_time"]), float(rec["answer_end_time"])
    if b < a:
        a, b = b, a
    return any(a <= t <= b for t in ts)


def build_request(rec, construction):
    """Frame timestamps actually sent, and the OpenAI content array for them."""
    qt = float(rec["question_time"])
    n = DI.choose_n(rec)
    want = DI.frame_times_for(construction, qt, n)
    avail = [t for t, _ in cached_frames(rec["video_id"])]
    by_t = {t: p for t, p in cached_frames(rec["video_id"])}
    ts = DI.nearest_available(want, sorted(avail))
    items = [(t, DI.resize_560_b64(by_t[t])) for t in ts]
    return ts, n, DI.build_chat_content(rec, items)


def extract_answer(text, reasoning):
    """Answer letter from the content channel; reasoning is never parsed for it."""
    t = (text or "").strip()
    if t and t[0] in "ABCDE" and (len(t) == 1 or t[1] in ".\n ):,"):
        return t[0], "direct"
    m = re.search(r'(?:answer is|answer:|the answer)\s*[:\s]*([A-E])\b', t, re.IGNORECASE)
    if m:
        return m.group(1).upper(), "extracted"
    hits = LETTER.findall(t[-300:])
    if hits:
        return hits[-1], "last_found"
    return None, "no_letter"


# ---------------------------------------------------------------------------

def start_server(lm, mmproj, port, ngl=99, ctx=16384):
    """Orin flags verbatim: --jinja --reasoning-format deepseek -ngl 99 -fa on -c 16384."""
    cmd = [str(LLAMA_SERVER), "-m", str(lm), "--mmproj", str(mmproj),
           "--jinja", "--reasoning-format", "deepseek", "-ngl", str(ngl),
           "-fa", "on", "-c", str(ctx), "--seed", str(SERVER_SEED),
           "--host", "127.0.0.1", "--port", str(port)]
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="1")
    print("launching: " + " ".join(cmd), flush=True)
    log = open(OUT_DIR / f"llamaserver_{port}.log", "w")
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=env,
                            preexec_fn=os.setsid)
    url = f"http://127.0.0.1:{port}"
    for _ in range(600):
        if proc.poll() is not None:
            raise SystemExit(f"FATAL: llama-server died; see {log.name}")
        try:
            if requests.get(url + "/health", timeout=2).status_code == 200:
                print("server ready", flush=True)
                return proc, url
        except Exception:
            pass
        time.sleep(1)
    raise SystemExit("FATAL: llama-server did not become ready in 600 s")


def stop_server(proc):
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=60)
    except Exception:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell", required=True, choices=list(CELLS))
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--qids", default=None, help="comma-separated question_ids (probe / Orin sample)")
    ap.add_argument("--orin-sample", action="store_true",
                    help="restrict to the Orin's 120-question latency sample")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    spec = CELLS[args.cell]
    print(f"cell {args.cell}: {spec['model']} x DEV-{spec['construction']}  gen={spec['gen']}",
          flush=True)
    lm, mmproj = verify_models(spec["model"])

    recs = load_pool()
    if args.orin_sample:
        keep = set(json.load(open(ORIN_SAMPLE))["question_ids"])
        recs = [r for r in recs if r["question_id"] in keep]
    if args.qids:
        keep = set(args.qids.split(","))
        recs = [r for r in recs if r["question_id"] in keep]
    if args.limit:
        recs = recs[:args.limit]
    print(f"{len(recs)} questions", flush=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"_{args.tag}" if args.tag else ""
    jsonl = OUT_DIR / f"accuracy_{args.cell}{suffix}.jsonl"
    done = set()
    if jsonl.exists():
        for line in open(jsonl):
            try:
                done.add(json.loads(line)["question_id"])
            except Exception:
                continue
        print(f"resuming: {len(done)} already done", flush=True)

    proc, url = start_server(lm, mmproj, args.port)
    n_done = n_correct = 0
    lat = []
    t_start = time.time()
    try:
        with open(jsonl, "a") as f:
            for rec in recs:
                if rec["question_id"] in done:
                    continue
                ts, n_target, content = build_request(rec, spec["construction"])
                body = dict(messages=[{"role": "user", "content": content}],
                            stream=False, seed=SERVER_SEED, **spec["gen"])
                t0 = time.time()
                resp = requests.post(url + "/v1/chat/completions", json=body, timeout=3600)
                lat_ms = (time.time() - t0) * 1000
                resp.raise_for_status()
                j = resp.json()
                msg = j["choices"][0]["message"]
                reasoning = msg.get("reasoning_content") or ""
                answer = msg.get("content") or ""
                usage = j.get("usage", {})
                finish = j["choices"][0].get("finish_reason")

                pred, parse_status = extract_answer(answer, reasoning)
                gold = rec["correct_letter"]
                ok = (pred == gold)

                trial = {
                    "cell": args.cell,
                    "model": spec["model"],
                    "construction": spec["construction"],
                    "question_id": rec["question_id"],
                    "video_id": rec["video_id"],
                    "question_category": rec.get("question_category"),
                    "question_time": rec["question_time"],
                    "frame_timestamps": ts,
                    "n_frames": len(ts),
                    "n_frames_target": n_target,
                    "evidence_covered": covered(ts, rec),
                    "answer_start_time": rec.get("answer_start_time"),
                    "answer_end_time": rec.get("answer_end_time"),
                    "n_input_tokens": usage.get("prompt_tokens"),
                    "n_output_tokens": usage.get("completion_tokens"),
                    "predicted_letter": pred,
                    "correct_letter": gold,
                    "correct": ok,
                    "parse_status": parse_status,
                    "answer_text": answer,
                    "reasoning_text": reasoning if spec["model"].startswith("4B-T") else None,
                    "n_think_tokens": (len(reasoning.split()) if reasoning else 0),
                    "think_closed": (bool(answer.strip()) if spec["model"].startswith("4B-T")
                                     else None),
                    "budget_hit": finish == "length",
                    "finish_reason": finish,
                    "latency_ms": round(lat_ms, 1),
                    "seed": SERVER_SEED,
                    "gguf_lm": lm.name,
                    "gguf_lm_sha256": MODELS[spec["model"]]["lm_sha"],
                }
                f.write(json.dumps(trial) + "\n")
                f.flush()

                n_done += 1
                n_correct += int(ok)
                lat.append(lat_ms)
                if n_done == 5 or n_done % 25 == 0 or n_done == len(recs):
                    mean_s = sum(lat) / len(lat) / 1000
                    remain = len(recs) - len(done) - n_done
                    print(f"[{args.cell}] {n_done}/{len(recs)-len(done)} "
                          f"acc={n_correct}/{n_done} ({100*n_correct/n_done:.1f}%) "
                          f"mean={mean_s:.1f}s in_tok={usage.get('prompt_tokens')} "
                          f"proj_remaining={mean_s*remain/3600:.2f}h", flush=True)
    finally:
        stop_server(proc)

    elapsed_h = (time.time() - t_start) / 3600
    print(f"\nDONE {args.cell}: n={n_done} acc={n_correct}/{n_done} "
          f"({100*n_correct/max(1,n_done):.1f}%) elapsed={elapsed_h:.2f}h", flush=True)
    meta = {
        "cell": args.cell, "model": spec["model"], "construction": spec["construction"],
        "gen": spec["gen"], "server_flags": "--jinja --reasoning-format deepseek -ngl 99 "
                                            "-fa on -c 16384", "seed": SERVER_SEED,
        "llamacpp_commit": "c0fd78626405c6d9b934efef0ec7291fcc20e3d6",
        "gguf_lm": lm.name, "gguf_lm_sha256": MODELS[spec["model"]]["lm_sha"],
        "gguf_mmproj": mmproj.name, "gguf_mmproj_sha256": MODELS[spec["model"]]["mmproj_sha"],
        "n_trials": n_done, "n_correct": n_correct, "elapsed_h": round(elapsed_h, 3),
        "frame_cache": str(FRAME_CACHE), "jsonl": str(jsonl.relative_to(ROOT)),
        "_provenance": stamp(script="device_tier_accuracy.py", model=spec["model"],
                             device="a6000", n=n_done, seed=SERVER_SEED, args=args),
    }
    json.dump(meta, open(OUT_DIR / f"accuracy_{args.cell}{suffix}_meta.json", "w"), indent=2)


if __name__ == "__main__":
    main()
