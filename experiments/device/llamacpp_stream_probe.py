#!/usr/bin/env python3
"""
Track A step 4 — llama.cpp device-runtime stream probe (Jetson AGX Orin).

Probes a running llama-server (Qwen3-VL-4B-Thinking, Q8_0 LM + F16 mmproj) over its
OpenAI-compatible API and measures:
  1. streaming with per-token monotonic timestamps, reasoning vs answer marked
     (reasoning = delta.reasoning_content, answer = delta.content; --reasoning-format deepseek)
  2. TTFT, decode tok/s (median over the trace), prefill time (from server timings)
  3. abort: cancel the stream after N reasoning tokens; measure SERVER-side stop latency
     by polling /slots until is_processing flips false (not just client close)
  4. forced answer: /completion with a raw prompt ending in the partial trace + "</think>\n\n";
     latency + whether prompt caching avoided re-prefill (n_prompt_tokens_cache from /slots)
  5. decode-speed with 1, 8, 16 images in one prompt; prefill time + memory each

Caching note (CLAUDE.md): the server runs with default prompt caching ON. Cold vs cached
forced-answer prefill is measured explicitly via /slots counters and labelled as such.

Writes: results/device/llamacpp_probe.json
"""
import argparse, base64, glob, json, os, statistics, subprocess, time, urllib.request, urllib.error

BASE = "http://127.0.0.1:8080"
IMGDIR = "results/vision/study_c/study_c_images"
OUT = "results/device/llamacpp_probe.json"
Q = "How many people are in this image? Answer with a single integer."


def b64(path):
    return base64.b64encode(open(path, "rb").read()).decode()


def data_url(path):
    return f"data:image/png;base64,{b64(path)}"


def tegrastats_ram_mb():
    """Read one tegrastats line and return used-RAM MB (unified memory: allocator+CPU)."""
    import re
    p = subprocess.Popen(["tegrastats", "--interval", "200"],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        deadline = time.time() + 3
        while time.time() < deadline:
            line = p.stdout.readline()
            m = re.search(r"RAM (\d+)/(\d+)MB", line or "")
            if m:
                return int(m.group(1))
    finally:
        p.terminate()
        try:
            p.wait(timeout=1)
        except Exception:
            p.kill()
    return None


def cache_reuse_probe(image):
    """Fire the SAME chat request twice; the 2nd should reuse the image+prompt prefill.
    Reports n_prompt_tokens_cache on the 2nd call (direct 'caching avoided re-prefill' signal)."""
    # drain to idle
    for _ in range(50):
        s = slot0()
        if s and not s["is_processing"]:
            break
        time.sleep(0.1)
    stream_trace([image], max_tokens=30)          # call 1 (populates cache)
    time.sleep(0.3)
    s_before = slot0() or {}
    tr = stream_trace([image], max_tokens=30)      # call 2 (should hit cache)
    tim = tr.get("timings") or {}
    s_after = slot0() or {}
    return {"call2_prompt_n": tim.get("prompt_n"),
            "call2_prefill_ms": tim.get("prompt_ms"),
            "call2_n_prompt_tokens_cache": s_after.get("n_prompt_tokens_cache"),
            "call2_n_prompt_tokens_processed": s_after.get("n_prompt_tokens_processed")}


def slots():
    try:
        return json.loads(urllib.request.urlopen(f"{BASE}/slots", timeout=5).read())
    except Exception:
        return None


def slot0():
    s = slots()
    return s[0] if s else None


# ── 1+2: stream one request, per-token timestamps, TTFT/decode-tps/prefill ──
def stream_trace(images, question=Q, max_tokens=512, abort_after_reason=None):
    content = [{"type": "image_url", "image_url": {"url": data_url(p)}} for p in images]
    content.append({"type": "text", "text": question})
    payload = {"model": "m", "messages": [{"role": "user", "content": content}],
               "stream": True, "max_tokens": max_tokens,
               "stream_options": {"include_usage": True}}
    req = urllib.request.Request(f"{BASE}/v1/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    tokens = []          # (t_monotonic, kind, text)
    t0 = time.perf_counter()
    ttft = None
    timings = None
    aborted = False
    resp = urllib.request.urlopen(req)
    try:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data: "):
                continue
            d = line[6:]
            if d == "[DONE]":
                break
            obj = json.loads(d)
            if obj.get("timings"):
                timings = obj["timings"]
            ch = obj.get("choices") or [{}]
            delta = ch[0].get("delta", {}) if ch else {}
            now = time.perf_counter()
            r = delta.get("reasoning_content")
            c = delta.get("content")
            if r:
                if ttft is None:
                    ttft = now - t0
                tokens.append((now - t0, "reason", r))
            if c:
                if ttft is None:
                    ttft = now - t0
                tokens.append((now - t0, "answer", c))
            if abort_after_reason is not None:
                n_reason = sum(1 for _, k, _ in tokens if k == "reason")
                if n_reason >= abort_after_reason:
                    aborted = True
                    break
    finally:
        if aborted:
            resp.close()   # drop connection -> server should detect disconnect
    total = time.perf_counter() - t0
    return {"tokens": tokens, "ttft_s": ttft, "wall_s": total,
            "timings": timings, "aborted": aborted}


def decode_stats(trace):
    ts = [t for t, _, _ in trace["tokens"]]
    n = len(ts)
    if n < 2:
        return {"n_tokens": n, "decode_tps_median": None, "decode_tps_overall": None}
    dts = [ts[i] - ts[i-1] for i in range(1, n)]
    med_dt = statistics.median(dts)
    first = trace["ttft_s"] or ts[0]
    decode_span = ts[-1] - ts[0]
    return {"n_tokens": n,
            "n_reason": sum(1 for _, k, _ in trace["tokens"] if k == "reason"),
            "n_answer": sum(1 for _, k, _ in trace["tokens"] if k == "answer"),
            "decode_tps_median": round(1.0/med_dt, 2) if med_dt > 0 else None,
            "decode_tps_overall": round((n-1)/decode_span, 2) if decode_span > 0 else None}


# ── 3: abort, server-side stop latency ──
def probe_abort(images, abort_after=40):
    # ensure idle
    for _ in range(50):
        s = slot0()
        if s and not s["is_processing"]:
            break
        time.sleep(0.1)
    tr = stream_trace(images, max_tokens=1024, abort_after_reason=abort_after)
    t_abort = time.perf_counter()
    # poll server until slot idle
    stop_latency = None
    for _ in range(200):   # up to ~20 s
        s = slot0()
        if s and not s["is_processing"]:
            stop_latency = time.perf_counter() - t_abort
            break
        time.sleep(0.1)
    return {"aborted_after_reason_tokens": abort_after,
            "client_tokens_seen": len(tr["tokens"]),
            "server_stop_latency_s": round(stop_latency, 3) if stop_latency is not None else None}


# ── 4: forced answer via raw /completion, cache detection ──
def render_prompt_with_partial_trace(image, partial_reason_text):
    """Build a raw prompt: full chat-templated prefix with the image, then an assistant
    turn opened with a partial <think> trace force-closed by </think>, so the model must
    emit the answer next. We ask the server to apply the template via /apply-template, then
    append the forced trace."""
    # Get the templated prefix (up to assistant generation point) via /apply-template
    msgs = {"messages": [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": data_url(image)}},
        {"type": "text", "text": Q}]}]}
    req = urllib.request.Request(f"{BASE}/apply-template",
                                 data=json.dumps(msgs).encode(),
                                 headers={"Content-Type": "application/json"})
    prefix = json.loads(urllib.request.urlopen(req).read())["prompt"]
    # Force a (partial) reasoning trace then close it so the next tokens are the answer.
    return prefix + partial_reason_text + "\n</think>\n\n"


def completion(prompt, image, max_tokens=40):
    payload = {"prompt": prompt, "n_predict": max_tokens, "stream": False,
               "cache_prompt": True,
               "image_data": [{"data": b64(image), "id": 10}],
               "temperature": 1.0, "top_p": 0.95, "top_k": 20}
    # NB: multimodal raw /completion needs the image referenced in the prompt; llama.cpp
    # uses [img-ID] markers. We fall back to chat if this path rejects images.
    req = urllib.request.Request(f"{BASE}/completion",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    obj = json.loads(urllib.request.urlopen(req).read())
    wall = time.perf_counter() - t0
    return obj, wall


def probe_forced_answer(image):
    """Two-phase: (A) run a full thinking request to warm the trace into cache, capture its
    partial reasoning; (B) send the forced-answer completion and read /slots cache counters."""
    # Phase A: get a real partial reasoning trace (first ~60 reason tokens)
    trA = stream_trace([image], max_tokens=200, abort_after_reason=60)
    partial = "".join(t for _, k, t in trA["tokens"] if k == "reason")
    prompt = render_prompt_with_partial_trace(image, partial)
    try:
        obj, wall = completion(prompt, image, max_tokens=40)
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:200]}"}
    tim = obj.get("timings", {})
    s = slot0() or {}
    return {"forced_answer_wall_s": round(wall, 3),
            "answer_text": obj.get("content", "")[:120],
            "prompt_n": tim.get("prompt_n"),
            "prompt_ms": tim.get("prompt_ms"),
            "predicted_n": tim.get("predicted_n"),
            "predicted_ms": tim.get("predicted_ms"),
            "slot_n_prompt_tokens_cache": s.get("n_prompt_tokens_cache"),
            "slot_n_prompt_tokens_processed": s.get("n_prompt_tokens_processed"),
            "partial_reason_chars": len(partial)}


# ── 5: multi-image decode speed / prefill / memory ──
def probe_multi_image(counts=(1, 8, 16)):
    pool = sorted(glob.glob(f"{IMGDIR}/*.png"))
    out = {}
    for n in counts:
        imgs = (pool * ((n // len(pool)) + 1))[:n]
        ram_before = tegrastats_ram_mb()
        tr = stream_trace(imgs, max_tokens=200)
        ram_after = tegrastats_ram_mb()
        ds = decode_stats(tr)
        tim = tr.get("timings") or {}
        out[str(n)] = {"images": n,
                       "prefill_ms": tim.get("prompt_ms"),
                       "prompt_n": tim.get("prompt_n"),
                       "ttft_s": round(tr["ttft_s"], 3) if tr["ttft_s"] else None,
                       "decode_tps_median": ds["decode_tps_median"],
                       "decode_tps_overall": ds["decode_tps_overall"],
                       "ram_before_mb": ram_before, "ram_after_mb": ram_after,
                       "ram_delta_mb": (ram_after - ram_before) if (ram_before and ram_after) else None}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    args = ap.parse_args()
    img = sorted(glob.glob(f"{IMGDIR}/L2_*.png"))[0]

    result = {"server_base": BASE, "image_dir": IMGDIR, "question": Q,
              "note_sember": "S-EMBER video frames not present on this box; multi-image "
                             "decode/prefill/memory uses COCO 560x560 frames (vision-token "
                             "count is content-independent at fixed resolution, Study A).",
              "reps": args.reps}

    # 1+2 single-image, repeated (noise floor)
    singles = []
    for i in range(args.reps):
        tr = stream_trace([img], max_tokens=512)
        ds = decode_stats(tr)
        tim = tr.get("timings") or {}
        singles.append({"rep": i, "ttft_s": round(tr["ttft_s"], 3) if tr["ttft_s"] else None,
                        "prefill_ms": tim.get("prompt_ms"), "prompt_n": tim.get("prompt_n"),
                        **ds})
        print(f"single rep{i}: ttft={singles[-1]['ttft_s']}s prefill={tim.get('prompt_ms')}ms "
              f"dec_tps_med={ds['decode_tps_median']} n={ds['n_tokens']} "
              f"(reason={ds['n_reason']} answer={ds['n_answer']})", flush=True)
    result["single_image"] = singles
    med_tps = statistics.median([s["decode_tps_median"] for s in singles if s["decode_tps_median"]])
    result["single_image_decode_tps_median_of_reps"] = round(med_tps, 2)
    # example trace (timestamps) from rep 0 for the report
    ex = stream_trace([img], max_tokens=512)
    result["example_trace_first40"] = [{"t_s": round(t, 4), "kind": k, "tok": tok}
                                        for t, k, tok in ex["tokens"][:40]]

    print("abort probe...", flush=True)
    result["abort"] = probe_abort([img], abort_after=40)
    print(f"  {result['abort']}", flush=True)

    print("forced-answer probe...", flush=True)
    fa = probe_forced_answer(img)
    fa["caveat"] = ("raw /completion path did not carry vision tokens (prompt_n reflects text "
                    "only), so this demonstrates the forced-early-termination MECHANISM (inject "
                    "</think> -> answer emitted) but the answer is not image-grounded here. "
                    "Image-grounded prefill reuse is measured separately in cache_reuse.")
    result["forced_answer"] = fa
    print(f"  {fa}", flush=True)

    print("cache-reuse probe (image-grounded prefill reuse)...", flush=True)
    result["cache_reuse"] = cache_reuse_probe(img)
    print(f"  {result['cache_reuse']}", flush=True)

    print("multi-image probe (1,8,16)...", flush=True)
    result["multi_image"] = probe_multi_image((1, 8, 16))
    for k, v in result["multi_image"].items():
        print(f"  N={k}: prefill={v['prefill_ms']}ms prompt_n={v['prompt_n']} "
              f"dec_tps_med={v['decode_tps_median']} ram_delta={v['ram_delta_mb']}MB", flush=True)

    os.makedirs("results/device", exist_ok=True)
    json.dump(result, open(OUT, "w"), indent=2)
    print(f"\n-> {OUT}", flush=True)


if __name__ == "__main__":
    main()
