#!/usr/bin/env python3
"""StudySS1 runner: send one manifest's questions to an OpenAI-compatible model endpoint (vLLM),
one request at a time, greedy, and write per-question JSON (answer, score, TTFT, prompt tokens,
output tokens). The SAME runner serves the device (Orin, Qwen3-VL-4B) and the H100 cloud (32B), so
the two tiers are produced by identical code. Scores computed here are deterministic from the
answer: VizWiz VQA accuracy, and EgoThink scorer (b) containment. EgoThink scorer (a), the judge,
is a separate pass (ss1_judge.py).

Caching: vLLM prefix caching is enabled on the server, but every request carries a distinct image
and question, so no warm prefix is reused across questions; a per-request cache_salt is also sent.
Each question is therefore a cold single-shot. Greedy decoding (temperature 0, seed 0). No em dashes.

Usage:
  python3 ss1_run.py --dataset vizwiz  --manifest results/casestudy/study_ss1/vizwiz_val_manifest.jsonl \
      --ids results/casestudy/study_ss1/vizwiz_pilot300.json --tier device --model qwen3vl4b \
      --out results/casestudy/study_ss1/vizwiz_pilot_device.json
  (--ids all  runs the whole manifest)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ss1_kit as K   # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = Path("/dev/shm/ss1_data")


def load_rows(manifest, ids_arg):
    rows = [json.loads(l) for l in Path(manifest).read_text().splitlines() if l.strip()]
    if ids_arg == "all":
        return rows
    want = set(json.loads(Path(ids_arg).read_text())["qids"])
    by = {r["qid"]: r for r in rows}
    return [by[q] for q in sorted(want) if q in by]


def image_path(row):
    img = row["image"]
    if img.startswith("egothink_images/"):
        return DATA / img
    return DATA / "vizwiz" / "val" / img


def call(endpoint, model, prompt, data_url, max_tokens, salt, timeout=180):
    """Stream the chat completion; return (text, ttft_s, total_s, prompt_tokens, completion_tokens).
    TTFT is the wall time to the first non-empty content delta."""
    body = dict(
        model=model, temperature=0.0, seed=0, max_tokens=max_tokens, stream=True,
        stream_options={"include_usage": True}, cache_salt=str(salt),
        messages=[{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": data_url}}]}])
    t0 = time.monotonic()
    ttft = None
    chunks = []
    pt = ct = None
    with requests.post(endpoint.rstrip("/") + "/chat/completions", json=body, stream=True,
                       timeout=timeout) as r:
        r.raise_for_status()
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            d = json.loads(payload)
            if d.get("usage"):
                pt = d["usage"].get("prompt_tokens")
                ct = d["usage"].get("completion_tokens")
            for ch in d.get("choices", []):
                piece = (ch.get("delta") or {}).get("content")
                if piece:
                    if ttft is None:
                        ttft = time.monotonic() - t0
                    chunks.append(piece)
    total = time.monotonic() - t0
    return "".join(chunks), ttft, total, pt, ct


def score_row(dataset, row, answer):
    if dataset == "vizwiz":
        return dict(vqa_accuracy=K.vqa_accuracy(answer, row["references"]))
    cont = K.egothink_containment(answer, row["references"][0])
    return dict(containment=cont)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, choices=["vizwiz", "egothink"])
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--ids", default="all")
    ap.add_argument("--tier", required=True, choices=["device", "cloud"])
    ap.add_argument("--model", required=True)
    ap.add_argument("--endpoint", default="http://127.0.0.1:8000/v1")
    ap.add_argument("--out", required=True)
    ap.add_argument("--retries", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0, help="debug: cap number of questions")
    a = ap.parse_args()

    rows = load_rows(a.manifest, a.ids)
    if a.limit:
        rows = rows[:a.limit]
    out_rows = []
    t_start = time.time()
    n_err = 0
    for i, row in enumerate(rows):
        prompt = (K.vizwiz_prompt(row["question"]) if a.dataset == "vizwiz"
                  else K.egothink_prompt(row["question"]))
        data_url = K.jpeg_data_url(str(image_path(row)))
        text = None
        for att in range(a.retries + 1):
            try:
                text, ttft, total, pt, ct = call(a.endpoint, a.model, prompt, data_url,
                                                 row["gen_max_new_tokens"], row["qid"])
                break
            except Exception as e:
                if att >= a.retries:
                    out_rows.append(dict(qid=row["qid"], error=repr(e)[:200]))
                    n_err += 1
                    text = None
                    break
                time.sleep(1.5 * (att + 1))
        if text is None:
            continue
        answer = (K.egothink_clean_output(text) if a.dataset == "egothink" else text.strip())
        rec = dict(qid=row["qid"], dataset=a.dataset, tier=a.tier, model=a.model,
                   question=row["question"], references=row["references"],
                   prompt=prompt, answer_raw=text, answer=answer,
                   ttft_s=ttft, total_s=total, prompt_tokens=pt, completion_tokens=ct,
                   score=score_row(a.dataset, row, answer))
        for k in ("answer_type", "answerable", "dimension", "area"):
            if k in row:
                rec[k] = row[k]
        out_rows.append(rec)
        if (i + 1) % 25 == 0 or i == len(rows) - 1:
            print("  %s %s %d/%d  errs=%d  elapsed=%.0fs" %
                  (a.dataset, a.tier, i + 1, len(rows), n_err, time.time() - t_start), flush=True)

    res = dict(study="StudySS1", dataset=a.dataset, tier=a.tier, model=a.model,
               endpoint=a.endpoint, n=len(rows), n_scored=sum(1 for r in out_rows if "error" not in r),
               n_errors=n_err, ids=a.ids, decoding="greedy temperature=0 seed=0 one-at-a-time",
               caching="vLLM prefix caching on; distinct image+question per request so no warm "
                       "reuse; per-request cache_salt=qid; cold single-shot",
               seconds=time.time() - t_start, rows=out_rows)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=1, default=float))
    print("wrote", a.out, "scored", res["n_scored"], "errors", n_err, "in %.0fs" % res["seconds"])


if __name__ == "__main__":
    main()
