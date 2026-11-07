"""StudyB1-flash runner. One GPU, one model, both arms, both inputs.

Descriptive capability pass. No latency is measured or claimed from this host.
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures as cf
import datetime as dt
import gzip
import hashlib
import json
import os
import queue
import random
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import b1_frames as FR
import b1_parse as PA

REPO = Path("/home/pragya/Desktop/FM-switching")
RES = REPO / "results/benchmarks/study_b1_flash"
IDX = RES / "index"
VENV = Path("/mnt/ssd/hf_models/venvs/fm-switching-vllm")
HUB = Path("/mnt/ssd/hf_models")

MODELS = {
    "4B": {
        "Instruct": ("Qwen/Qwen3-VL-4B-Instruct", "ebb281ec70b05090aa6165b016eac8ec08e71b17"),
        "Thinking": ("Qwen/Qwen3-VL-4B-Thinking", "1de27d8c51f12e819435303b9e84c4e25ba8401e"),
    },
    "8B": {
        "Instruct": ("Qwen/Qwen3-VL-8B-Instruct", "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"),
        "Thinking": ("Qwen/Qwen3-VL-8B-Thinking", "92f3c4b4feadd3a016ef468d103bb5f58b2a2c6b"),
    },
}

# ---------------------------------------------------------------- prompt template
HEADER = ("You are given {n} frames extracted from a video, ordered oldest first.\n"
          "They are the only visual information available.\n")
ANSWER_LETTER = "\nAnswer with the letter of the best option and nothing else."

TEMPLATES = {
    "letter": HEADER + "\n{images}\nQuestion: {question}\nOptions:\n{options}" + ANSWER_LETTER,
    "count": HEADER + "\n{images}\n{question}\n"
             "Provide your answer as a single number (e.g., 0, 1, 2, 3...) indicating the total "
             "count.\nDo not include any additional text or explanation in your response.",
    "yesno": HEADER + "\n{images}\n{question}\n"
             "Answer only with “Yes” or “No”.\n"
             "Do not include any additional text or explanation in your response.",
}
TEMPLATE_SHA = hashlib.sha256(
    json.dumps(TEMPLATES, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

DATASET_ORDER_S1 = [
    ("ovo_bench", "forward"), ("ovo_bench", "other"), ("rtv_bench", None),
    ("streaming_bench", None), ("herbench", "lite_v2"), ("herbench", "rest"),
]
DATASET_ORDER_S2 = [
    ("ovo_bench", "forward"), ("ovo_bench", "other"), ("rtv_bench", None),
    ("streaming_bench", None), ("herbench", "lite_v2"),
]


def now() -> dt.datetime:
    return dt.datetime.now()


def log(msg: str):
    print(f"[{now():%H:%M:%S}] {msg}", flush=True)


def build_prompt(row, n_frames):
    kind = row["answer_kind"]
    if kind == "letter":
        opts = "\n".join(f"{k}. {row['options'][k]}" for k in sorted(row["options"]))
        return TEMPLATES["letter"].format(n=n_frames, images="", question=row["question"],
                                          options=opts).replace("\n\n\n", "\n\n")
    return TEMPLATES[kind].format(n=n_frames, images="", question=row["question"]
                                  ).replace("\n\n\n", "\n\n")


def to_messages(row, pngs):
    """Header text, then the images oldest first, then question/options, then the instruction.

    No timestamps and no file names anywhere in the prompt.
    """
    kind = row["answer_kind"]
    head = HEADER.format(n=len(pngs))
    if kind == "letter":
        opts = "\n".join(f"{k}. {row['options'][k]}" for k in sorted(row["options"]))
        tail = f"Question: {row['question']}\nOptions:\n{opts}{ANSWER_LETTER}"
    elif kind == "count":
        tail = (f"{row['question']}\nProvide your answer as a single number "
                "(e.g., 0, 1, 2, 3...) indicating the total count.\n"
                "Do not include any additional text or explanation in your response.")
    else:
        tail = (f"{row['question']}\nAnswer only with “Yes” or “No”.\n"
                "Do not include any additional text or explanation in your response.")
    content = [{"type": "text", "text": head}]
    for p in pngs:
        content.append({"type": "image_url", "image_url": {
            "url": "data:image/png;base64," + base64.b64encode(p).decode()}})
    content.append({"type": "text", "text": tail})
    return [{"role": "user", "content": content}], head + "\n<IMAGES x%d>\n" % len(pngs) + tail


# ---------------------------------------------------------------- server
def free_port(p):
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", p))
        return True
    except OSError:
        return False
    finally:
        s.close()


def start_server(gpu, model_key, arm, port, logdir):
    repo, rev = MODELS[model_key][arm]
    snap = HUB / f"models--{repo.replace('/', '--')}" / "snapshots" / rev
    assert snap.exists(), snap
    served = f"{model_key}{arm[0]}"
    cmd = [str(VENV / "bin/vllm"), "serve", str(snap),
           "--served-model-name", served,
           "--port", str(port),
           "--max-model-len", "32768",
           "--gpu-memory-utilization", "0.90",
           "--tensor-parallel-size", "1",
           "--no-enable-prefix-caching",
           "--limit-mm-per-prompt", json.dumps({"image": FR.HISTORY_N, "video": 0}),
           "--mm-processor-cache-gb", "0",
           "--dtype", "bfloat16",
           "--seed", "0",
           "--host", "127.0.0.1"]
    env = dict(os.environ)
    env["CUDA_VISIBLE_DEVICES"] = str(gpu)
    env["HF_HOME"] = str(HUB)
    env["VLLM_USE_FLASHINFER_SAMPLER"] = "0"
    lf = logdir / f"server_{served}_{now():%m%d_%H%M%S}.log"
    fh = open(lf, "w")
    p = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT, env=env,
                         start_new_session=False)
    log(f"server {served} pid={p.pid} gpu={gpu} port={port} log={lf.name}")
    return p, lf, served, cmd, repo, rev


def wait_ready(port, proc, timeout=1200):
    import urllib.request
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            raise RuntimeError(f"server died rc={proc.returncode}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as r:
                if r.status == 200:
                    return time.time() - t0
        except Exception:
            time.sleep(3)
    raise TimeoutError("server not ready")


def stop_server(proc):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(120)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(60)


# ---------------------------------------------------------------- work
def load_index(name):
    return [json.loads(l) for l in open(IDX / f"{name}.jsonl")]


def select(rows, name, part):
    if name == "ovo_bench":
        if part == "forward":
            return [r for r in rows if r["ovo_group"] == "forward"]
        return [r for r in rows if r["ovo_group"] != "forward"]
    if name == "herbench":
        if part == "lite_v2":
            return [r for r in rows if r["lite_v2"]]
        return [r for r in rows if not r["lite_v2"]]
    return rows


class Out:
    def __init__(self, path, cap=90 * 1024 * 1024):
        self.base, self.cap, self.part = path, cap, 0
        self.lock = threading.Lock()
        self.done = set()
        self._scan()
        self._open()

    def _name(self, i):
        return self.base.parent / f"{self.base.name}.part{i:03d}.jsonl.gz"

    def _scan(self):
        i = 0
        while self._name(i).exists():
            try:
                with gzip.open(self._name(i), "rt") as fh:
                    for line in fh:
                        try:
                            self.done.add(json.loads(line)["key"])
                        except Exception:
                            pass
            except (EOFError, OSError):
                pass
            i += 1
        self.part = max(0, i - 1)

    def _open(self):
        self.fh = gzip.open(self._name(self.part), "at")

    def write(self, rec):
        with self.lock:
            self.fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self.fh.flush()
            if self._name(self.part).stat().st_size > self.cap:
                self.fh.close()
                self.part += 1
                self._open()

    def close(self):
        with self.lock:
            self.fh.close()


def grey_pngs(n):
    import io
    from PIL import Image
    img = Image.new("RGB", (FR.OUT_W, FR.OUT_H), (128, 128, 128))
    b = io.BytesIO()
    img.save(b, format="PNG")
    return [b.getvalue()] * n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpu", type=int, required=True)
    ap.add_argument("--model", required=True, choices=list(MODELS))
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--render-threads", type=int, default=12)
    ap.add_argument("--stop-at", default="2026-11-06T09:00:00")
    ap.add_argument("--stage2-at", default="2026-11-06T05:00:00")
    ap.add_argument("--min-free-gb", type=float, default=50.0)
    a = ap.parse_args()

    stop_at = dt.datetime.fromisoformat(a.stop_at)
    stage2_at = dt.datetime.fromisoformat(a.stage2_at)
    outdir = RES / f"model_{a.model}"
    outdir.mkdir(parents=True, exist_ok=True)
    logdir = REPO / "logs"
    logdir.mkdir(exist_ok=True)

    index = {n: load_index(n) for n in ("rtv_bench", "ovo_bench", "herbench", "streaming_bench")}
    out = Out(outdir / "requests")
    log(f"resume: {len(out.done)} rows already present")

    meta_path = outdir / "run_meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {"servers": [], "events": []}
    meta["frames_spec"] = {
        "code_path": "experiments/benchmarks/b1_frames.py",
        "code_sha256": hashlib.sha256((REPO / "experiments/benchmarks/b1_frames.py").read_bytes()).hexdigest(),
        "parse_path": "experiments/benchmarks/b1_parse.py",
        "parse_sha256": hashlib.sha256((REPO / "experiments/benchmarks/b1_parse.py").read_bytes()).hexdigest(),
        "run_path": "experiments/benchmarks/b1_run.py",
        "recent_n": FR.RECENT_N, "recent_span_s": FR.RECENT_SPAN_S,
        "history_n": FR.HISTORY_N, "out_wh": [FR.OUT_W, FR.OUT_H],
        "resize": "PIL LANCZOS", "encode": "PNG lossless",
        "versions": FR.versions(),
        "template_sha256": TEMPLATE_SHA, "templates": TEMPLATES,
    }
    meta["concurrency"] = a.concurrency
    meta["render_threads"] = a.render_threads
    meta_path.write_text(json.dumps(meta, indent=1))

    import urllib.error
    import urllib.request

    stopflag = {"stop": False, "reason": None}

    def disk_ok():
        st = os.statvfs("/mnt/ssd")
        gb = st.f_bavail * st.f_frsize / 1024**3
        if gb < a.min_free_gb:
            stopflag["stop"] = True
            stopflag["reason"] = f"free disk on /mnt/ssd {gb:.1f} GB < {a.min_free_gb} GB"
            return False
        return True

    def call(served, msgs, arm):
        if arm == "Instruct":
            body = {"model": served, "messages": msgs, "temperature": 0.0,
                    "max_tokens": 64, "logprobs": True, "top_logprobs": 20, "seed": 0}
        else:
            body = {"model": served, "messages": msgs, "temperature": 1.0, "top_p": 0.95,
                    "max_tokens": 16384, "seed": 0, "extra_body": {"top_k": 20}}
            body["top_k"] = 20
        data = json.dumps(body).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{a.port}/v1/chat/completions",
                                     data=data, headers={"Content-Type": "application/json"})
        last = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=1800) as r:
                    return json.loads(r.read()), attempt, None
            except urllib.error.HTTPError as e:
                # a real server error is not retried
                return None, attempt, f"HTTP {e.code}: {e.read()[:400].decode(errors='replace')}"
            except Exception as e:
                last = f"{type(e).__name__}: {e}"
                time.sleep(2 + 3 * attempt)
        return None, 2, last

    counters = {"ok": 0, "fail": 0, "skip": 0}

    def one(row, mode, arm, served, grey=False, gidx=0):
        assert isinstance(served, str) and served, f"served must be the model name, got {served!r}"
        assert isinstance(grey, bool), f"grey must be bool, got {grey!r}"
        key = f"{a.model}|{arm}|{mode}|{'GREY' if grey else row['dataset']}|{row['qid'] if not grey else gidx}"
        if key in out.done:
            counters["skip"] += 1
            return
        if stopflag["stop"]:
            return
        t_render0 = time.time()
        try:
            if grey:
                n = FR.RECENT_N if mode == "RECENT" else FR.HISTORY_N
                pngs = grey_pngs(n)
                fmeta = {"mode": mode, "grey": True, "n_frames": n,
                         "frame_sha256": [hashlib.sha256(pngs[0]).hexdigest()] * n}
            else:
                pngs, fmeta = FR.render(row["video"], mode, row["t"])
        except Exception as e:
            out.write({"key": key, "model": a.model, "arm": arm, "mode": mode,
                       "dataset": row["dataset"], "qid": row.get("qid"), "grey": grey,
                       "error": f"render: {type(e).__name__}: {e}", "ts": now().isoformat()})
            counters["fail"] += 1
            return
        render_s = time.time() - t_render0

        msgs, prompt_text = to_messages(row, pngs)
        t0 = time.time()
        resp, attempts, err = call(served, msgs, arm)
        wall = time.time() - t0

        rec = {"key": key, "model": a.model, "arm": arm, "mode": mode,
               "dataset": row["dataset"], "task": row.get("task"), "qid": row.get("qid"),
               "video_key": row.get("video_key"), "grey": grey,
               "gold": row["gold"], "answer_kind": row["answer_kind"],
               "t_query_s": row.get("t"), "order": row.get("order"),
               "render_s": round(render_s, 3), "wall_s": round(wall, 3),
               "retries": attempts, "ts": now().isoformat(),
               "frames": {k: v for k, v in fmeta.items()},
               "prompt_sha256": hashlib.sha256(prompt_text.encode()).hexdigest()}
        if row["dataset"] == "herbench":
            rec["required_timestamps"] = row.get("required_timestamps")
            rec["lite_v2"] = row.get("lite_v2")
        if row["dataset"] == "ovo_bench":
            rec["ovo_group"] = row.get("ovo_group")

        if resp is None:
            rec["error"] = err
            counters["fail"] += 1
        else:
            ch = resp["choices"][0]
            raw = ch["message"]["content"] or ""
            usage = resp.get("usage", {})
            rec["finish_reason"] = ch.get("finish_reason")
            rec["truncated"] = ch.get("finish_reason") == "length"
            rec["gen_tokens"] = usage.get("completion_tokens")
            rec["prompt_tokens"] = usage.get("prompt_tokens")
            rec.update(PA.score(row, raw))
            if arm == "Thinking":
                rec["response_gz_b64"] = base64.b64encode(
                    gzip.compress(raw.encode())).decode()
            else:
                rec["response"] = raw[:2000]
                lp = ch.get("logprobs")
                if lp and lp.get("content"):
                    rec["top_logprobs_first"] = [
                        {"token": d["token"], "logprob": d["logprob"]}
                        for d in (lp["content"][0].get("top_logprobs") or [])][:20]
            counters["ok"] += 1
        out.write(rec)

    def run_batch(items, served, arm, pool):
        # items are (row, mode, arm, grey, gidx); `served` must go in slot 4
        futs = [pool.submit(one, it[0], it[1], it[2], served, it[3], it[4]) for it in items]
        for f in cf.as_completed(futs):
            f.result()

    # ------------------------------------------------ arms
    for arm in ("Instruct", "Thinking"):
        if now() >= stop_at or stopflag["stop"]:
            break
        if arm == "Thinking" and now() < stage2_at:
            # stage 1 still has budget; it is run to completion below before the swap
            pass
        proc, lf, served, cmd, repo, rev = start_server(a.gpu, a.model, arm, a.port, logdir)
        try:
            startup = wait_ready(a.port, proc)
            meta["servers"].append({"model": a.model, "arm": arm, "repo": repo, "revision": rev,
                                    "cmd": cmd, "gpu": a.gpu, "startup_s": round(startup, 1),
                                    "log": lf.name, "started": now().isoformat(),
                                    "vllm": "0.19.1"})
            meta_path.write_text(json.dumps(meta, indent=1))
            log(f"{served} ready in {startup:.1f}s")

            with cf.ThreadPoolExecutor(max_workers=a.concurrency) as pool:
                # grey-frame controls: 100 per arm per input
                grey_row = {"dataset": "GREY", "qid": None, "task": "grey", "gold": "A",
                            "answer_kind": "letter", "options": {"A": "one", "B": "two",
                            "C": "three", "D": "four"}, "question": "What is shown?",
                            "parser": "strict", "video_key": "GREY", "t": None}
                for mode in ("RECENT", "HISTORY"):
                    items = [(grey_row, mode, arm, True, i) for i in range(100)]
                    run_batch(items, served, arm, pool)
                    log(f"grey {arm}/{mode} done  ok={counters['ok']} "
                        f"fail={counters['fail']} skip={counters['skip']}")
                    if counters["ok"] + counters["skip"] == 0:
                        raise RuntimeError("grey control produced no successful rows")
                    if not disk_ok():
                        break

                order = DATASET_ORDER_S1 if arm == "Instruct" else DATASET_ORDER_S2
                if arm == "Instruct":
                    for mode in ("RECENT", "HISTORY"):
                        for name, part in order:
                            if name == "herbench" and mode == "RECENT":
                                continue
                            rows = select(index[name], name, part)
                            B = 64
                            for i in range(0, len(rows), B):
                                if now() >= stop_at or stopflag["stop"]:
                                    break
                                if arm == "Instruct" and now() >= stage2_at:
                                    log("05:00 reached -> leaving stage 1 for stage 2")
                                    break
                                run_batch([(r, mode, arm, False, 0) for r in rows[i:i + B]],
                                          served, arm, pool)
                                if not disk_ok():
                                    break
                            log(f"S1 {mode} {name}/{part} ok={counters['ok']} "
                                f"fail={counters['fail']} skip={counters['skip']} "
                                f"cache={FR.cache_stats()['entries']}")
                            if now() >= stop_at or stopflag["stop"] or now() >= stage2_at:
                                break
                        if now() >= stop_at or stopflag["stop"] or now() >= stage2_at:
                            break
                else:
                    # alternate batches of 200 among the five sets so all progress
                    pools = {}
                    for name, part in order:
                        rows = select(index[name], name, part)
                        for mode in ("RECENT", "HISTORY"):
                            if name == "herbench" and mode == "RECENT":
                                continue
                            pools[(name, part, mode)] = list(rows)
                    pos = {k: 0 for k in pools}
                    while not stopflag["stop"] and now() < stop_at:
                        progressed = False
                        for k in list(pools):
                            if now() >= stop_at or stopflag["stop"]:
                                break
                            rows, p = pools[k], pos[k]
                            if p >= len(rows):
                                continue
                            chunk = rows[p:p + 200]
                            pos[k] = p + len(chunk)
                            progressed = True
                            name, part, mode = k
                            for i in range(0, len(chunk), 32):
                                if now() >= stop_at or stopflag["stop"]:
                                    break
                                run_batch([(r, mode, arm, False, 0) for r in chunk[i:i + 32]],
                                          served, arm, pool)
                                if not disk_ok():
                                    break
                            log(f"S2 {name}/{part}/{mode} {pos[k]}/{len(rows)} "
                                f"ok={counters['ok']} fail={counters['fail']}")
                        if not progressed:
                            break
        finally:
            stop_server(proc)
            meta["events"].append({"arm": arm, "stopped": now().isoformat(),
                                   "counters": dict(counters),
                                   "stop_reason": stopflag["reason"]})
            meta_path.write_text(json.dumps(meta, indent=1))
            log(f"server {served} stopped. counters={counters}")

    out.close()
    meta["finished"] = now().isoformat()
    meta["final_counters"] = dict(counters)
    meta["frame_cache"] = FR.cache_stats()
    meta_path.write_text(json.dumps(meta, indent=1))
    log(f"DONE {counters} stop_reason={stopflag['reason']}")


if __name__ == "__main__":
    main()
