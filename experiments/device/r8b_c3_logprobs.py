#!/usr/bin/env python3
"""StudyR8b — C3 re-run with per-generated-token log-probabilities, seeds 1 and 2.

Cell C3 of StudyDevAcc-llamacpp, re-run exactly (same llama.cpp commit, same GGUF
sha256, same server flags, same DEV-RECENT inputs, same sampling, same 845 questions,
same parsing) with `logprobs: true, top_logprobs: 20` added to each request. Request
construction, model verification, server start/stop and answer parsing are IMPORTED
from experiments/device/device_tier_accuracy.py, not copied.

llama-server maps OpenAI `logprobs`/`top_logprobs` onto its own `n_probs`
(tools/server/server-common.cpp) and, with `post_sampling_probs` left at its default
false, returns PRE-sampling-chain log-probabilities for every generated token
(tools/server/server-context.cpp). `choices[0].logprobs.content` is the whole
generated_token_probs vector, so reasoning tokens are expected to be covered; Step 0
is the gate that checks it rather than assuming it.

Durations recorded here are CONTENDED (R8a and R8c share the host by the scheduling
rule) and are not latency measurements.
"""
import argparse, gzip, json, os, sys, time
from pathlib import Path

os.environ.setdefault("O_FRAME_CACHE", "/home/pragya/device_tier/oframes")

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "experiments" / "lib"))

import device_tier_accuracy as DTA
from _provenance import stamp

OUT_DIR = ROOT / "results/device"
TOPK = 20
TOP20_REASONING_LIMIT = 400     # pre-registered size fallback
SHARD_BYTES = 18 * 1024 * 1024


def strip_think(s):
    return s.replace("<think>", "").replace("</think>", "")


def split_channels(toks, reasoning_text, answer_text):
    """Mark each returned token as reasoning or answer by walking the concatenation.

    The deepseek reasoning format splits the message into reasoning_content and
    content; the logprobs array is the undivided token stream. A token belongs to the
    reasoning channel while the running concatenation (with think tags removed) is
    still inside reasoning_text.
    """
    n_r = len(reasoning_text)
    chan, run = [], 0
    for t in toks:
        piece = strip_think(t)
        chan.append("r" if run < n_r else "a")
        run += len(piece)
    return "".join(chan)


def gate_check(toks, reasoning_text, answer_text, completion_tokens):
    joined = strip_think("".join(toks))
    target = (reasoning_text or "") + (answer_text or "")
    return dict(
        n_entries=len(toks),
        completion_tokens=completion_tokens,
        count_matches=(completion_tokens is None or len(toks) == completion_tokens),
        exact_text_match=(joined == target),
        stripped_text_match=("".join(joined.split()) == "".join(target.split())),
        n_reasoning_chars=len(reasoning_text or ""),
        n_answer_chars=len(answer_text or ""),
        joined_len=len(joined), target_len=len(target),
    )


def request_one(url, rec, gen, seed, logprobs=True, timeout=3600):
    ts, n_target, content = DTA.build_request(rec, "RECENT")
    body = dict(messages=[{"role": "user", "content": content}], stream=False,
                seed=seed, **gen)
    if logprobs:
        body["logprobs"] = True
        body["top_logprobs"] = TOPK
    t0 = time.time()
    resp = requests.post(url + "/v1/chat/completions", json=body, timeout=timeout)
    dur_ms = (time.time() - t0) * 1000
    resp.raise_for_status()
    j = resp.json()
    return ts, n_target, j, dur_ms


def parse_logprobs(j):
    ch = j["choices"][0]
    lp = (ch.get("logprobs") or {}).get("content") or []
    toks = [e.get("token", "") for e in lp]
    chosen = [round(float(e.get("logprob", 0.0)), 4) for e in lp]
    tops = []
    for e in lp:
        tl = e.get("top_logprobs") or []
        tops.append(([int(x.get("id", -1)) for x in tl],
                     [round(float(x.get("logprob", 0.0)), 4) for x in tl]))
    return toks, chosen, tops


class ShardWriter:
    def __init__(self, stem):
        self.stem, self.n, self.f, self.paths = stem, 0, None, []
        self._roll()

    def _roll(self):
        if self.f:
            self.f.close()
        self.n += 1
        p = Path(f"{self.stem}_part{self.n:02d}.jsonl.gz")
        self.f = gzip.open(p, "at")
        self.paths.append(p)

    def write(self, obj):
        self.f.write(json.dumps(obj) + "\n")
        self.f.flush()
        if self.paths[-1].stat().st_size > SHARD_BYTES:
            self._roll()

    def close(self):
        if self.f:
            self.f.close()
        return [p for p in self.paths if p.stat().st_size > 20]


def cached_ok(rec):
    d = Path(os.environ["O_FRAME_CACHE"]) / rec["video_id"] / "index.json"
    if not d.exists():
        return False
    try:
        return json.load(open(d))["max_qt"] >= float(rec["question_time"]) - 1
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["step0", "run"], required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--port", type=int, default=8101)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    spec = DTA.CELLS["C3"]
    gen = dict(spec["gen"])
    lm, mmproj = DTA.verify_models(spec["model"])
    recs = DTA.load_pool()
    print(f"pool {len(recs)} questions; frame cache {os.environ['O_FRAME_CACHE']}", flush=True)

    if args.mode == "step0":
        ready = [r for r in recs if cached_ok(r)][:3]
        if len(ready) < 3:
            raise SystemExit(f"STEP 0: only {len(ready)} questions have cached frames yet")
        proc, url = DTA.start_server(lm, mmproj, args.port)
        out = {"questions": [], "temp0_control": []}
        try:
            for rec in ready:
                ts, nt, j, dur = request_one(url, rec, gen, args.seed)
                msg = j["choices"][0]["message"]
                toks, chosen, tops = parse_logprobs(j)
                g = gate_check(toks, msg.get("reasoning_content") or "",
                               msg.get("content") or "", j.get("usage", {}).get("completion_tokens"))
                chan = split_channels(toks, msg.get("reasoning_content") or "",
                                      msg.get("content") or "")
                g.update(n_reasoning_tokens=chan.count("r"), n_answer_tokens=chan.count("a"),
                         n_top_entries_first=len(tops[0][0]) if tops else 0,
                         first_tokens=toks[:12],
                         chosen_lp_head=chosen[:8],
                         contended_duration_s=round(dur / 1000, 1),
                         question_id=rec["question_id"])
                out["questions"].append(g)
                print(json.dumps(g, indent=1)[:900], flush=True)
                # Step 4 control: the same question at temperature 0
                g0 = dict(gen, temperature=0.0)
                g0.pop("top_p", None); g0.pop("top_k", None)
                _, _, j0, _ = request_one(url, rec, g0, args.seed)
                t0k, c0, _ = parse_logprobs(j0)
                out["temp0_control"].append(dict(
                    question_id=rec["question_id"], n_entries=len(t0k),
                    mean_chosen_logprob=round(sum(c0) / max(1, len(c0)), 4)))
        finally:
            DTA.stop_server(proc)
        for a, b in zip(out["questions"], out["temp0_control"]):
            a["mean_chosen_logprob_t1"] = round(
                sum(a["chosen_lp_head"]) / max(1, len(a["chosen_lp_head"])), 4)
        passed = all(q["count_matches"] and (q["exact_text_match"] or q["stripped_text_match"])
                     and q["n_reasoning_tokens"] > 0 for q in out["questions"])
        out["gate_passed"] = bool(passed)
        p = OUT_DIR / "r8b_step0_probe.json"
        json.dump(out, open(p, "w"), indent=1)
        print(f"\nSTEP 0 GATE: {'PASS' if passed else 'FAIL'} -> {p}", flush=True)
        return

    # ---------------- full run ----------------
    if args.limit:
        recs = recs[:args.limit]
    missing = [r for r in recs if not cached_ok(r)]
    if missing:
        raise SystemExit(f"FATAL: {len(missing)} questions have no frame cache yet")

    stem = OUT_DIR / f"accuracy_C3_logprobs_s{args.seed}"
    writer = ShardWriter(str(stem))
    proc, url = DTA.start_server(lm, mmproj, args.port)
    n_done = n_correct = 0
    truncated_any = 0
    t_start = time.time()
    try:
        for rec in recs:
            ts, n_target, j, dur_ms = request_one(url, rec, gen, args.seed)
            msg = j["choices"][0]["message"]
            reasoning = msg.get("reasoning_content") or ""
            answer = msg.get("content") or ""
            usage = j.get("usage", {})
            finish = j["choices"][0].get("finish_reason")
            toks, chosen, tops = parse_logprobs(j)
            chan = split_channels(toks, reasoning, answer)
            n_r = chan.count("r")
            keep = min(n_r, TOP20_REASONING_LIMIT)
            if n_r > TOP20_REASONING_LIMIT:
                truncated_any += 1
            pred, parse_status = DTA.extract_answer(answer, reasoning)
            gold = rec["correct_letter"]
            ok = (pred == gold)
            writer.write({
                "cell": "C3_logprobs", "model": spec["model"], "construction": "RECENT",
                "question_id": rec["question_id"], "video_id": rec["video_id"],
                "question_category": rec.get("question_category"),
                "question_time": rec["question_time"], "frame_timestamps": ts,
                "n_frames": len(ts), "n_frames_target": n_target,
                "evidence_covered": DTA.covered(ts, rec),
                "answer_start_time": rec.get("answer_start_time"),
                "answer_end_time": rec.get("answer_end_time"),
                "n_input_tokens": usage.get("prompt_tokens"),
                "n_output_tokens": usage.get("completion_tokens"),
                "predicted_letter": pred, "correct_letter": gold, "correct": ok,
                "parse_status": parse_status, "answer_text": answer,
                "reasoning_text": reasoning,
                "n_think_tokens": (len(reasoning.split()) if reasoning else 0),
                "n_think_tokens_real": n_r,
                "think_closed": bool(answer.strip()),
                "budget_hit": finish == "length", "finish_reason": finish,
                "contended_duration_ms": round(dur_ms, 1),
                "seed": args.seed, "gguf_lm": lm.name,
                "gguf_lm_sha256": DTA.MODELS[spec["model"]]["lm_sha"],
                "n_logprob_entries": len(toks),
                "logprob_entries_equal_completion_tokens":
                    (usage.get("completion_tokens") is None or len(toks) == usage["completion_tokens"]),
                "tokens": {
                    "text": toks, "chosen_lp": chosen, "channel": chan,
                    "top20_ids": [tops[i][0] for i in range(keep)],
                    "top20_lp": [tops[i][1] for i in range(keep)],
                    "top20_covers": f"reasoning tokens 0-{keep - 1}" if keep else "none",
                },
            })
            n_done += 1
            n_correct += int(ok)
            if n_done == 3 or n_done % 25 == 0 or n_done == len(recs):
                el = time.time() - t_start
                print(f"[r8b s{args.seed}] {n_done}/{len(recs)} acc={n_correct}/{n_done} "
                      f"({100*n_correct/n_done:.1f}%) elapsed={el/3600:.2f}h "
                      f"proj={el/n_done*len(recs)/3600:.2f}h", flush=True)
    finally:
        DTA.stop_server(proc)
        paths = writer.close()

    elapsed_h = (time.time() - t_start) / 3600
    meta = {
        "study": "StudyR8b", "cell": "C3_logprobs", "seed": args.seed,
        "n_trials": n_done, "n_correct": n_correct,
        "accuracy_pct": round(100 * n_correct / max(1, n_done), 3),
        "elapsed_h": round(elapsed_h, 3), "contended": True,
        "contention_note": "R8a (CPU) and R8c (3090 Ti) shared the host; every duration "
                           "recorded here is contended, not a latency measurement",
        "model": spec["model"], "gen": gen,
        "server_flags": "--jinja --reasoning-format deepseek -ngl 99 -fa on -c 16384",
        "logprobs": dict(requested_top_k=TOPK, post_sampling_probs=False,
                         note="llama-server returns PRE-sampling-chain logprobs; the "
                              "temperature/top-p/top-k chain is NOT applied to them"),
        "top20_truncated_questions": truncated_any,
        "top20_rule": f"top-{TOPK} kept for reasoning tokens 0-{TOP20_REASONING_LIMIT - 1}; "
                      "chosen logprob kept for every token",
        "files": [str(p.relative_to(ROOT)) for p in paths],
        "file_sizes_mb": [round(p.stat().st_size / 1e6, 3) for p in paths],
        "_provenance": stamp(script="r8b_c3_logprobs.py", model="qwen3vl4b_thinking_gguf_f16",
                             device="a6000", n=n_done, seed=args.seed, args=args),
    }
    mp = OUT_DIR / f"accuracy_C3_logprobs_s{args.seed}_meta.json"
    json.dump(meta, open(mp, "w"), indent=2)
    print(f"\nDONE r8b s{args.seed}: n={n_done} acc={n_correct}/{n_done} "
          f"({100*n_correct/max(1,n_done):.1f}%) elapsed={elapsed_h:.2f}h -> {mp}", flush=True)


if __name__ == "__main__":
    main()
