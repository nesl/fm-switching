#!/usr/bin/env python3
"""
StudyE8-device-warm — cost of keeping a 4B D2 history warm on the Jetson Orin.

Jetson Orin only. Same stack as StudyF4 / StudyD8: llama.cpp c0fd786,
Qwen3VL-4B-Instruct-F16 (+mmproj-F16), sha256 verified; MAXN mode 0, GPU pinned
1.3005 GHz (verified + logged per request); greedy (temperature 0), seed 0,
max_tokens 64. n_ctx large (57344) so the longest D2 history (52,127 tok) fits.

Inputs: StudyE7-d2-4b Job C archive /home/nesl/data/study_e7_d2_frames/e7/
  requests/<qid>.json  74 D2 question requests (header + ordered images + text,
                       gen block, R1 parser, expected_prompt_tokens, body_sha256)
  frames/<video>/t<sec>.png   4,521 PNG frames (one every 2 s from session start)
  sha256_manifest.json        per-file sha256 (hard-verified before any run)
  videos.json                 20 videos, 4 length bins x 5
  letters_4b.jsonl            H100 StudyE7 4B letters (parity source; 6 over_context -> pred None)

Parts:
  0  MECHANISM GATE: does llama.cpp reuse the IMAGE KV prefix across append / question?
     append(history) -> append(history+frame) -> question -> append(+frame). The appends
     must evaluate ~one frame's tokens and reuse the rest. If not, STOP (mechanism absent).
  A  WARM REPLAY (20 sessions): append one frame per request (prefill-only, max_tokens 1),
     insert history+question at each question time; log evaluated/reused/TTFT/total/energy/clock.
  B  COLD REFERENCE: 30 question requests across the token range, cache_prompt false.
  C  SUSTAINED KEEP-WARM: one long session real-time 10 min after 120 s idle baseline.
  D  PARITY: device letters (warm + cold) vs H100 StudyE7 4B on identical bytes.

Outputs under results/device/study_e8/.
"""
import argparse, base64, hashlib, json, math, os, re, statistics as st, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import experiments.device.dev_fast_latency as dfl
from experiments.lib._provenance import stamp

ROOT = Path(__file__).resolve().parent.parent.parent
OUTDIR = ROOT / "results/device/study_e8"
E7DIR = Path("/home/nesl/data/study_e7_d2_frames/e7")
REQDIR = E7DIR / "requests"
FRAMES = E7DIR          # request image paths are "frames/<video>/..." relative to e7/
MANIFEST = E7DIR / "sha256_manifest.json"
VIDEOS = E7DIR / "videos.json"
LETTERS = E7DIR / "letters_4b.jsonl"
MANIFEST_BASE = E7DIR.parent  # manifest keys are "e7/frames/..."

MODEL_TAG = "4bi_f16"
PINNED_HZ = 1300500000
MAX_TOKENS = 64
N_CTX = 57344
SEED = 0                      # task-mandated; request block carries seed 42 (immaterial under greedy)
TOP_LOGPROBS = 20            # honor E7 request block (F4 used 5)
GEN_Q = dict(temperature=0.0, max_tokens=MAX_TOKENS, seed=SEED)
GEN_APPEND = dict(temperature=0.0, max_tokens=1, seed=SEED)
STOP_TJ = 90.0
D_REF_ORIN = {"note": "StudyD4-orin/F4 cold TTFT p50 N=1/3/9 = 0.513/1.34/3.84 s (3/9 frames); E8 cold curve is per-prompt-token"}
FRAME_TOK_EST = 90          # ~tokens per 560x560 D2 frame (from expected_prompt_tokens spread)


# ── parser (E7 R1): last standalone A-E in the final 300 chars, else X ────────
def parse_r1(text):
    tail = (text or "")[-300:]
    ms = re.findall(r"(?<![A-Za-z])([A-E])(?![A-Za-z])", tail)
    return ms[-1] if ms else "X"


def pct(xs, q):
    xs = sorted(v for v in xs if v is not None)
    if not xs:
        return None
    if len(xs) == 1:
        return round(xs[0], 4)
    i = q / 100 * (len(xs) - 1)
    lo = int(i); hi = min(lo + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (i - lo), 4)


def recent_tj(sampler, n=30):
    rows = sampler.snapshot()[-n:]
    tjs = [r["tj"] for r in rows if r.get("tj")]
    return max(tjs) if tjs else None


# ── inputs ───────────────────────────────────────────────────────────────────
def verify_inputs():
    man = json.load(open(MANIFEST))
    bad = []; miss = []; n = 0
    for rel, want in man.items():
        p = MANIFEST_BASE / rel
        if not p.exists():
            miss.append(rel); continue
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        n += 1
        if h != want:
            bad.append(rel)
    ok = (not bad and not miss)
    print(f"input sha256: ok={n}/{len(man)} bad={len(bad)} missing={len(miss)}", flush=True)
    if not ok:
        print("BAD:", bad[:5], "MISSING:", miss[:5], flush=True)
    return ok, n, len(man)


def load_requests():
    """Return {qid: req} and videos.json."""
    reqs = {}
    for f in sorted(REQDIR.glob("*.json")):
        d = json.load(open(f))
        reqs[d["question_id"]] = d
    vids = json.load(open(VIDEOS))
    return reqs, vids


_LETTERS = None
def load_letters():
    global _LETTERS
    if _LETTERS is None:
        _LETTERS = {json.loads(l)["question_id"]: json.loads(l) for l in open(LETTERS)}
    return _LETTERS


def frames_for_video(video_id):
    """All D2 frames for a video in stride (time) order."""
    d = FRAMES / "frames" / video_id
    fs = sorted(d.glob("t*.png"), key=lambda p: float(p.stem[1:]))
    return [f"frames/{video_id}/{p.name}" for p in fs]


def frame_t(rel):
    return float(Path(rel).stem[1:])


def b64_image(rel):
    b = base64.b64encode((E7DIR / rel).read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b}"}}


def build_append_content(header, frame_rels):
    """Keep-warm append: header text -> images (NO question). Strict image prefix."""
    content = [{"type": "text", "text": header}]
    for rel in frame_rels:
        content.append(b64_image(rel))
    return content


def build_question_content(req):
    """E7 assembly: header text -> images -> MCQ text (byte-identical to H100)."""
    content = [{"type": "text", "text": req["header"]}]
    for rel in req["images"]:
        content.append(b64_image(rel))
    content.append({"type": "text", "text": req["text"]})
    return content


def body_sha256(content):
    msgs = [{"role": "user", "content": content}]
    return hashlib.sha256(json.dumps(msgs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ── server (large context) ───────────────────────────────────────────────────
def launch_server_e8(log_path, n_ctx=N_CTX):
    import subprocess, signal
    weights, mmproj, fmt, gen = dfl.GGUF[MODEL_TAG]
    flags = ["-ngl", "99", "-fa", "on", "-c", str(n_ctx), "--jinja",
             "--reasoning-format", "deepseek", "--host", "127.0.0.1", "--port", "8080", "-np", "1"]
    cmd = [str(dfl.LLAMA), "-m", str(weights), "--mmproj", str(mmproj), *flags]
    log = open(log_path, "w")
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                            preexec_fn=os.setsid, stdin=subprocess.DEVNULL)
    t0 = time.time()
    while time.time() - t0 < 600:
        try:
            r = urllib.request.urlopen(f"{dfl.BASE}/health", timeout=2)
            if r.status == 200:
                print(f"  server up in {time.time()-t0:.0f}s (n_ctx={n_ctx})", flush=True)
                return proc
        except Exception:
            pass
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early (rc={proc.returncode}); see {log_path}")
        time.sleep(2)
    raise RuntimeError("server health timeout")


def parse_kv_mem(log_path):
    """Pull KV / context lines from the server log (this build prints no MiB; unified mem)."""
    out = {}
    try:
        txt = Path(log_path).read_text(errors="replace")
    except Exception:
        return out
    for pat, key in [
        (r"KV self size\s*=\s*([\d.]+)\s*MiB", "kv_self_mib"),
        (r"n_ctx_slot\s*=\s*(\d+)", "n_ctx_slot"),
        (r"kv_unified\s*=\s*'?(\w+)'?", "kv_unified"),
    ]:
        m = re.search(pat, txt)
        if m:
            g = m.group(1)
            out[key] = (float(g) if re.fullmatch(r"[\d.]+", g) and "." in g
                        else int(g) if g.isdigit() else g)
    out["note"] = "Jetson unified memory (no discrete VRAM); memory reported via server RSS + tegrastats peak RAM"
    return out


def server_rss_mib(proc):
    try:
        for l in open(f"/proc/{proc.pid}/status"):
            if l.startswith("VmRSS:"):
                return round(int(l.split()[1]) / 1024.0, 1)  # kB -> MiB
    except Exception:
        return None
    return None


def erase_slot(slot=0):
    """Clear a slot's prompt cache without restarting (fast session reset)."""
    try:
        req = urllib.request.Request(f"{dfl.BASE}/slots/{slot}?action=erase", method="POST",
                                     data=b"{}", headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
        return True
    except Exception as e:
        return False


# ── request ──────────────────────────────────────────────────────────────────
def req_raw(content, cache_prompt, gen, want_logprobs=True, timeout=600):
    payload = {"model": "m", "messages": [{"role": "user", "content": content}],
               "stream": True, "stream_options": {"include_usage": True}, **gen,
               "cache_prompt": cache_prompt}
    if want_logprobs:
        payload["logprobs"] = True
        payload["top_logprobs"] = TOP_LOGPROBS
    req = urllib.request.Request(f"{dfl.BASE}/v1/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    clk0 = dfl.gpu_freq()
    toks = []; lp_content = []
    wall_start = time.time(); t0 = time.perf_counter()
    ttft = None; timings = None; usage = None
    resp = urllib.request.urlopen(req, timeout=timeout)
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
        if o.get("usage"):
            usage = o["usage"]
        ch = o.get("choices") or [{}]
        c0 = ch[0] if ch else {}
        delta = c0.get("delta", {}) if c0 else {}
        lp = c0.get("logprobs") if c0 else None
        if lp and lp.get("content"):
            lp_content.extend(lp["content"])
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
    pred = parse_r1(ans if ans else rea)
    ans_lp = None
    for tk in lp_content:
        s = (tk.get("token") or "").strip()
        if re.fullmatch(r"[A-E]", s):
            ans_lp = {"token": s, "logprob": tk.get("logprob"),
                      "top": [{"token": (a.get("token") or "").strip(), "logprob": a.get("logprob")}
                              for a in (tk.get("top_logprobs") or [])][:TOP_LOGPROBS]}
            break
    tim = timings or {}
    usg = usage or {}
    prompt_total = usg.get("prompt_tokens")
    evaluated = tim.get("prompt_n")
    cache_n = tim.get("cache_n")
    reused = (prompt_total - evaluated) if (prompt_total is not None and evaluated is not None) else None
    return {
        "prompt_tokens": prompt_total, "evaluated": evaluated,
        "cache_n": cache_n, "reused": reused,
        "prefill_ms": tim.get("prompt_ms"), "n_gen": tim.get("predicted_n"),
        "ttft_s": round(ttft, 4) if ttft else None,
        "total_latency_s": round(total, 4),
        "answer_text": ans[:80], "pred": pred, "answer_logprob": ans_lp,
        "gpu_clock_before": clk0, "gpu_clock_after": clk1,
        "clock_ok": (clk0 == PINNED_HZ and clk1 == PINNED_HZ),
        "wall_start": wall_start, "wall_end": wall_end,
    }


# ── PART 0: mechanism gate ───────────────────────────────────────────────────
def part0(reqs, vids, log_path):
    """Pick a mid-size session; probe append/question KV reuse. Returns verdict dict."""
    # choose a video with a question around the middle so history is non-trivial but fast
    # prefer a ~30-frame history
    cand = None
    for v in vids["videos"]:
        vid = v["video_id"]
        fl = frames_for_video(vid)
        if 25 <= len(fl) <= 80:
            cand = (vid, fl); break
    if cand is None:
        v = vids["videos"][0]; cand = (v["video_id"], frames_for_video(v["video_id"]))
    vid, fl = cand
    # a question in this video (for the question-tail test); else synthesize a short question
    qreq = next((r for r in reqs.values() if r["video_id"] == vid), None)
    header = qreq["header"] if qreq else "[RH4_D2] device 00 session 0: egocentric camera history, one frame every 2 s from the session start."
    k = min(30, len(fl) - 2)                      # history length (frames)
    hist = fl[:k]
    qtext = qreq["text"] if qreq else "Question: placeholder?\n\nA. a\nB. b\nC. c\nD. d\nE. e\n\nReply with only the letter."
    print(f"Part 0 session={vid} history={k} frames", flush=True)

    erase_slot()
    r1 = req_raw(build_append_content(header, hist), cache_prompt=True, gen=GEN_APPEND, want_logprobs=False)         # history
    r2 = req_raw(build_append_content(header, fl[:k + 1]), cache_prompt=True, gen=GEN_APPEND, want_logprobs=False)   # +1 frame
    r3 = req_raw(build_question_content({"header": header, "images": fl[:k + 1], "text": qtext}),
                 cache_prompt=True, gen=GEN_Q)                                                                       # +question
    r4 = req_raw(build_append_content(header, fl[:k + 2]), cache_prompt=True, gen=GEN_APPEND, want_logprobs=False)   # +frame (question tail dropped)

    for nm, r in (("R1 history", r1), ("R2 +frame", r2), ("R3 +question", r3), ("R4 +frame", r4)):
        print(f"  {nm}: prompt={r['prompt_tokens']} evaluated={r['evaluated']} reused={r['reused']} "
              f"cache_n={r['cache_n']} ttft={r['ttft_s']}s", flush=True)

    # gate logic: warm append must reuse the image prefix (evaluated ~ one frame, not full)
    thresh = 3 * FRAME_TOK_EST          # generous: a frame + template tail
    r2_reuse = (r2["evaluated"] is not None and r2["evaluated"] <= thresh
                and r2["reused"] is not None and r2["reused"] >= r1["prompt_tokens"] - thresh)
    r4_reuse = (r4["evaluated"] is not None and r4["evaluated"] <= thresh
                and r4["reused"] is not None and r4["reused"] >= r2["prompt_tokens"] - thresh)
    passed = bool(r2_reuse and r4_reuse)
    verdict = {
        "video": vid, "history_frames": k, "frame_tok_est": FRAME_TOK_EST, "reuse_threshold": thresh,
        "R1_history": r1, "R2_plus_frame": r2, "R3_plus_question": r3, "R4_plus_frame": r4,
        "R2_reuses_image_prefix": r2_reuse, "R4_reuses_after_question_tail": r4_reuse,
        "passed": passed,
        "kv_mem": parse_kv_mem(log_path),
    }
    print(f"Part 0 VERDICT: passed={passed} (R2 reuse={r2_reuse}, R4 reuse={r4_reuse})", flush=True)
    return verdict


# ── PART A: warm replay ──────────────────────────────────────────────────────
def session_timeline(video_id, reqs):
    """Ordered events for a session: append each frame; before the frame whose t==qt (or just
    after reaching qt) insert the question. Returns list of ('append', frame_rel) / ('question', req)."""
    frames = frames_for_video(video_id)
    qs = sorted([r for r in reqs.values() if r["video_id"] == video_id], key=lambda r: r["question_time"])
    qi = 0
    events = []
    for rel in frames:
        t = frame_t(rel)
        # insert any question whose time <= current frame time, at the point its history is complete
        while qi < len(qs) and qs[qi]["question_time"] <= t:
            events.append(("question", qs[qi])); qi += 1
        events.append(("append", rel))
    while qi < len(qs):
        events.append(("question", qs[qi])); qi += 1
    return frames, qs, events


def part_a(reqs, vids, sampler, out_jsonl, resume=True):
    done = set()
    if resume and out_jsonl.exists():
        for l in open(out_jsonl):
            try:
                d = json.loads(l); done.add((d["video_id"], d["kind"], d.get("seq")))
            except Exception:
                pass
    f = open(out_jsonl, "a")
    vorder = [v["video_id"] for v in vids["videos"]]
    for vidx, vid in enumerate(vorder):
        frames, qs, events = session_timeline(vid, reqs)
        print(f"[A] session {vidx+1}/20 {vid} frames={len(frames)} qs={len(qs)}", flush=True)
        erase_slot()                      # clean slate per session
        hist_frames = []
        seq = 0
        for kind, item in events:
            seq += 1
            if (vid, kind, seq) in done:
                if kind == "append":
                    hist_frames.append(item)
                continue
            if kind == "append":
                hist_frames.append(item)
                content = build_append_content(reqs_header(reqs, vid), hist_frames)
                r = req_raw(content, cache_prompt=True, gen=GEN_APPEND, want_logprobs=False)
                row = {"video_id": vid, "kind": "append", "seq": seq,
                       "n_hist_frames": len(hist_frames), "frame_t": frame_t(item), **r}
            else:
                req = item
                content = build_question_content(req)
                r = req_raw(content, cache_prompt=True, gen=GEN_Q)
                let = load_letters().get(req["question_id"], {})
                row = {"video_id": vid, "kind": "question", "seq": seq,
                       "question_id": req["question_id"], "question_time": req["question_time"],
                       "question_category": req["question_category"],
                       "n_hist_frames": len(hist_frames), "n_images": len(req["images"]),
                       "expected_prompt_tokens": req["expected_prompt_tokens"],
                       "over_context": req.get("over_context", False),
                       "correct_letter": let.get("correct_letter"),
                       "h100_pred": let.get("pred_4b_h100"),
                       "body_sha256_match": body_sha256(content) == req["body_sha256"], **r}
                row["correct"] = (row["pred"] == row["correct_letter"]) if row["pred"] and row["pred"] != "X" else False
            f.write(json.dumps(row) + "\n"); f.flush()
            # throttle guard
            tj = recent_tj(sampler)
            if tj and tj >= STOP_TJ:
                print(f"STOP: tj={tj} >= {STOP_TJ}", flush=True); f.close(); return False
            if not r["clock_ok"]:
                print(f"WARN clock not pinned: {r['gpu_clock_before']}/{r['gpu_clock_after']}", flush=True)
        # progress line per session
        print(f"    session {vid} done ({seq} events)", flush=True)
    f.close()
    return True


_HEADER_CACHE = {}
def reqs_header(reqs, vid):
    if vid not in _HEADER_CACHE:
        r = next((r for r in reqs.values() if r["video_id"] == vid), None)
        _HEADER_CACHE[vid] = r["header"] if r else "[RH4_D2] device 00 session 0: egocentric camera history, one frame every 2 s from the session start."
    return _HEADER_CACHE[vid]


# ── PART B: cold reference ───────────────────────────────────────────────────
def part_b(reqs, sampler, out_jsonl, n=30):
    # stratify 30 questions over expected_prompt_tokens range (exclude over_context? keep in-range only
    # so cold prefill fits n_ctx; over_context (>n_ctx? no, 52127<57344 fits) keep all, pick spread)
    items = sorted(reqs.values(), key=lambda r: r["expected_prompt_tokens"])
    # even spread by index
    idx = [round(i * (len(items) - 1) / (n - 1)) for i in range(n)]
    picks = [items[i] for i in sorted(set(idx))]
    f = open(out_jsonl, "w")
    lets = load_letters()
    print(f"[B] cold reference: {len(picks)} questions", flush=True)
    for j, req in enumerate(picks):
        content = build_question_content(req)
        r = req_raw(content, cache_prompt=False, gen=GEN_Q)
        let = lets.get(req["question_id"], {})
        row = {"video_id": req["video_id"], "question_id": req["question_id"],
               "question_time": req["question_time"], "question_category": req["question_category"],
               "n_images": len(req["images"]), "expected_prompt_tokens": req["expected_prompt_tokens"],
               "over_context": req.get("over_context", False),
               "correct_letter": let.get("correct_letter"), "h100_pred": let.get("pred_4b_h100"),
               "body_sha256_match": body_sha256(content) == req["body_sha256"], **r}
        row["correct"] = (row["pred"] == row["correct_letter"]) if row["pred"] and row["pred"] != "X" else False
        f.write(json.dumps(row) + "\n"); f.flush()
        print(f"  [B] {j+1}/{len(picks)} tok={r['prompt_tokens']} reused={r['reused']} "
              f"ttft={r['ttft_s']}s total={r['total_latency_s']}s", flush=True)
        tj = recent_tj(sampler)
        if tj and tj >= STOP_TJ:
            print(f"STOP: tj={tj}", flush=True); break
    f.close()


# ── PART C: sustained keep-warm (real time) ──────────────────────────────────
def part_c(reqs, vids, sampler, out_jsonl, minutes=10, baseline_s=120):
    # pick the longest session
    longest = max(vids["videos"], key=lambda v: v["n_frames"])
    vid = longest["video_id"]
    frames, qs, events = session_timeline(vid, reqs)
    print(f"[C] keep-warm session {vid} frames={len(frames)} qs={len(qs)}", flush=True)
    erase_slot()
    # baseline (loaded idle, server up, nothing running)
    t0 = time.time()
    print(f"  baseline {baseline_s}s loaded-idle ...", flush=True)
    while time.time() - t0 < baseline_s:
        time.sleep(1)
    base_e = time.time()
    baseline = dfl.idle_stats(sampler.snapshot(), t0, base_e)
    print(f"  baseline: {baseline}", flush=True)

    f = open(out_jsonl, "w")
    warm_start = time.time()
    deadline = warm_start + minutes * 60
    hist_frames = []
    seq = 0
    next_append = warm_start
    ev_i = 0
    kept_up = True
    while time.time() < deadline and ev_i < len(events):
        kind, item = events[ev_i]; ev_i += 1
        if kind == "append":
            # pace: one append every 2 s of real time
            now = time.time()
            if now < next_append:
                time.sleep(next_append - now)
            hist_frames.append(item)
            seq += 1
            r = req_raw(build_append_content(reqs_header(reqs, vid), hist_frames),
                        cache_prompt=True, gen=GEN_APPEND, want_logprobs=False)
            late = (r["total_latency_s"] > 2.0)
            if late:
                kept_up = False
            row = {"video_id": vid, "kind": "append", "seq": seq, "n_hist_frames": len(hist_frames),
                   "frame_t": frame_t(item), "kept_up": not late, **r}
            next_append += 2.0
        else:
            req = item; seq += 1
            r = req_raw(build_question_content(req), cache_prompt=True, gen=GEN_Q)
            row = {"video_id": vid, "kind": "question", "seq": seq, "question_id": req["question_id"],
                   "question_time": req["question_time"], "n_hist_frames": len(hist_frames), **r}
        f.write(json.dumps(row) + "\n"); f.flush()
        tj = recent_tj(sampler)
        if tj and tj >= STOP_TJ:
            print(f"STOP: tj={tj}", flush=True); break
    warm_end = time.time()
    f.close()
    warm = dfl.idle_stats(sampler.snapshot(), warm_start, warm_end)  # mean power while warm (incl. appends)
    warm_energy = dfl.integrate(sampler.snapshot(), warm_start, warm_end)
    dur_h = (warm_end - warm_start) / 3600.0
    summary = {
        "video": vid, "minutes": minutes, "baseline_s": baseline_s,
        "baseline_idle": baseline, "warm_window": warm, "warm_energy": warm_energy,
        "warm_duration_s": round(warm_end - warm_start, 1),
        "mean_warm_w": warm["mean_total_w"] if warm else None,
        "mean_idle_w": baseline["mean_total_w"] if baseline else None,
        "delta_w": round(warm["mean_total_w"] - baseline["mean_total_w"], 4) if (warm and baseline) else None,
        "energy_per_warm_hour_wh": round(warm["mean_total_w"], 3) if warm else None,  # W == Wh/h
        "appends_kept_up": kept_up, "n_appends": sum(1 for k, _ in events[:ev_i] if k == "append"),
    }
    print(f"[C] summary: {json.dumps(summary)[:400]}", flush=True)
    return summary


# ── determinism control ──────────────────────────────────────────────────────
def determinism(reqs, sampler, n=10):
    req = min(reqs.values(), key=lambda r: r["expected_prompt_tokens"])  # cheap one
    letters = []
    erase_slot()
    for i in range(n):
        r = req_raw(build_question_content(req), cache_prompt=False, gen=GEN_Q, want_logprobs=False)
        letters.append(r["pred"])
    ident = len(set(letters)) == 1
    print(f"determinism: {letters} identical={ident}", flush=True)
    return {"question_id": req["question_id"], "letters": letters, "identical": ident, "n": n}


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts", default="0ABCD")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()
    OUTDIR.mkdir(parents=True, exist_ok=True)

    # preflight: clock pinned
    clk = dfl.gpu_freq()
    print(f"preflight clock={clk} pinned={PINNED_HZ} ok={clk == PINNED_HZ}", flush=True)

    if not args.no_verify:
        ok, n, tot = verify_inputs()
        if not ok:
            print("ABORT: input sha256 mismatch", flush=True); sys.exit(1)

    reqs, vids = load_requests()
    print(f"loaded {len(reqs)} requests, {len(vids['videos'])} videos", flush=True)

    log_path = OUTDIR / "server.log"
    proc = launch_server_e8(log_path)
    kvmem = parse_kv_mem(log_path)
    kvmem["server_rss_mib_postload"] = server_rss_mib(proc)
    kvmem["erase_endpoint_ok"] = erase_slot()
    print(f"kv_mem: {kvmem}", flush=True)

    base_gz = OUTDIR / "tegrastats.jsonl.gz"
    sampler = dfl.Sampler(str(base_gz))
    time.sleep(2)

    results = {"n_ctx": N_CTX, "kv_mem": kvmem, "stack": {
        "llama_cpp": "c0fd786", "model": MODEL_TAG, "seed": SEED, "top_logprobs": TOP_LOGPROBS,
        "parser": "R1 last standalone A-E in final 300 chars else X",
        "note_seed": "request block seed=42; using task-mandated 0 (immaterial under temp-0 greedy)"}}
    try:
        if "0" in args.parts:
            v0 = part0(reqs, vids, log_path)
            results["part0"] = v0
            json.dump(results, open(OUTDIR / "part0_mechanism.json", "w"), indent=2)
            if not v0["passed"]:
                print("MECHANISM GATE FAILED — stopping before Part A (warm mechanism absent).", flush=True)
                results["stopped_at"] = "part0"
                results["_provenance"] = stamp(script="study_e8_device_warm.py", model=MODEL_TAG,
                                                device="jetson_orin", n=0, args=args)
                json.dump(results, open(OUTDIR / "study_e8_summary.json", "w"), indent=2)
                return
        if args.smoke:
            print("smoke: Part 0 only (or determinism).", flush=True)
            results["determinism"] = determinism(reqs, sampler, n=3)
        else:
            if "A" in args.parts:
                ok = part_a(reqs, vids, sampler, OUTDIR / "partA_warm.jsonl")
                results["partA_complete"] = ok
            if "B" in args.parts:
                part_b(reqs, sampler, OUTDIR / "partB_cold.jsonl")
            if "D" in args.parts:
                results["determinism"] = determinism(reqs, sampler, n=10)
            if "C" in args.parts:
                results["partC"] = part_c(reqs, vids, sampler, OUTDIR / "partC_keepwarm.jsonl")
    finally:
        snap = sampler.snapshot()
        kvmem["server_rss_mib_peak"] = server_rss_mib(proc)
        kvmem["tegrastats_peak_ram_mib"] = max((r["ram_mb"] for r in snap if r.get("ram_mb")), default=None)
        results["kv_mem"] = kvmem
        sampler.stop()
        dfl.stop_server(proc)
        results["_provenance"] = stamp(script="study_e8_device_warm.py", model=MODEL_TAG,
                                       device="jetson_orin", n=len(reqs), args=args)
        json.dump(results, open(OUTDIR / "study_e8_summary.json", "w"), indent=2)
        print("StudyE8-device-warm run complete.", flush=True)


if __name__ == "__main__":
    main()
