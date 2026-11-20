#!/usr/bin/env python3
"""StudySS2 runner: send one manifest's items to an OpenAI-compatible model endpoint (vLLM), one
request at a time, greedy, and write per-question JSON (raw answer, parsed answer, score, TTFT,
prompt tokens, output tokens). The SAME runner serves the device (Orin, Qwen3-VL-4B) and the H100
cloud (32B), so the two tiers are produced by identical code. Scores are deterministic from the
answer: RefSpatial point-in-mask fraction, RealWorldQA exact match (MCQ letter / free-form string).

Caching: vLLM prefix caching is enabled on the server, but every request carries a distinct image
and task, so no warm prefix is reused across items; a per-request cache_salt is also sent. Each
item is therefore a cold single-shot. Greedy decoding (temperature 0, seed 0). No em dashes.

Usage:
  python3 ss2_run.py --dataset refspatial \
      --manifest results/casestudy/study_ss2/refspatial_manifest.jsonl \
      --ids all --tier device --model qwen3vl4b --device jetson_orin \
      --out results/casestudy/study_ss2/refspatial_device.json
  (--ids <smoke.json> runs just that id list; --dump prints raw output + parsed points per item)
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
sys.path.insert(0, str(HERE.parent / "lib"))
import ss2_bench_kit as K      # noqa: E402
from _provenance import stamp  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = Path("/dev/shm/ss2_data")


def load_rows(manifest, ids_arg):
    rows = [json.loads(l) for l in Path(manifest).read_text().splitlines() if l.strip()]
    if ids_arg == "all":
        return rows
    want = set(json.loads(Path(ids_arg).read_text())["qids"])
    by = {r["qid"]: r for r in rows}
    return [by[q] for q in sorted(want) if q in by]


def call(endpoint, model, prompt, data_url, max_tokens, salt, timeout=180, logprobs=False):
    """One single-shot request. With `logprobs`, the per-token top-20 is recorded as well.

    `logprobs` is OFF by default so this stays the function that produced the committed answers.
    The device-confidence re-record (user ruling 2026-11-20) turns it ON and changes nothing else:
    same prompt, same image, same greedy decoding and seed, so the ANSWERS must reproduce the
    committed ones and that equality is the re-record's own control.
    """
    body = dict(
        model=model, temperature=0.0, seed=0, max_tokens=max_tokens, stream=True,
        stream_options={"include_usage": True}, cache_salt=str(salt),
        messages=[{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": data_url}}]}])
    if logprobs:
        body["logprobs"] = True
        body["top_logprobs"] = 20
    t0 = time.monotonic()
    ttft = None
    chunks = []
    lp = []
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
                c = (ch.get("logprobs") or {}).get("content")
                if c:
                    lp.extend(c)
    if logprobs:
        return "".join(chunks), ttft, time.monotonic() - t0, pt, ct, lp
    return "".join(chunks), ttft, time.monotonic() - t0, pt, ct


def build_prompt(dataset, row):
    if dataset == "refspatial":
        return K.refspatial_prompt(row["object"])
    return K.realworldqa_prompt(row["question"])


def score_row(dataset, row, answer, dump=False):
    if dataset == "refspatial":
        mask = K.load_binary_mask(str(DATA / row["mask"]))
        H, W = mask.shape[:2]
        pts = K.refspatial_parse_points(answer, W, H)
        acc = K.refspatial_point_accuracy(pts, mask)
        rec = dict(point_accuracy=acc, n_points=int(len(pts)), split=row["split"], step=row["step"])
        if dump:
            rec["_points"] = pts.tolist()
            rec["_mask_wh"] = [W, H]
        return rec
    score, subset = K.realworldqa_score(answer, row["references"][0])
    return dict(exact_match=score, subset=subset)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, choices=["refspatial", "realworldqa"])
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--ids", default="all")
    ap.add_argument("--tier", required=True, choices=["device", "cloud"])
    ap.add_argument("--model", required=True)
    ap.add_argument("--device", default=None, help="provenance device slug, e.g. jetson_orin")
    ap.add_argument("--endpoint", default="http://127.0.0.1:8000/v1")
    ap.add_argument("--out", required=True)
    ap.add_argument("--retries", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dump", action="store_true", help="store parsed points + mask dims per item")
    a = ap.parse_args()

    rows = load_rows(a.manifest, a.ids)
    if a.limit:
        rows = rows[:a.limit]
    out_rows = []
    t_start = time.time()
    n_err = 0
    for i, row in enumerate(rows):
        prompt = build_prompt(a.dataset, row)
        data_url = K.jpeg_data_url(str(DATA / row["image"]))
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
        answer = text.strip()
        rec = dict(qid=row["qid"], dataset=a.dataset, tier=a.tier, model=a.model,
                   prompt=prompt, answer_raw=text, answer=answer,
                   references=row.get("references"), object=row.get("object"),
                   ttft_s=ttft, total_s=total, prompt_tokens=pt, completion_tokens=ct,
                   score=score_row(a.dataset, row, answer, dump=a.dump))
        out_rows.append(rec)
        if a.dump:
            print("  [%s] %s\n    -> %r\n    score=%s" %
                  (row["qid"], prompt[:80], text[:120], rec["score"]), flush=True)
        if (i + 1) % 25 == 0 or i == len(rows) - 1:
            print("  %s %s %d/%d  errs=%d  elapsed=%.0fs" %
                  (a.dataset, a.tier, i + 1, len(rows), n_err, time.time() - t_start), flush=True)

    res = dict(study="StudySS2", dataset=a.dataset, tier=a.tier, model=a.model,
               endpoint=a.endpoint, n=len(rows), n_scored=sum(1 for r in out_rows if "error" not in r),
               n_errors=n_err, ids=a.ids, coord_mode=K.COORD_MODE,
               decoding="greedy temperature=0 seed=0 one-at-a-time",
               caching="vLLM prefix caching on; distinct image+task per request so no warm reuse; "
                       "per-request cache_salt=qid; cold single-shot",
               seconds=time.time() - t_start, rows=out_rows)
    res["_provenance"] = stamp(script="ss2_run.py", model=a.model, device=a.device,
                               n=len(rows), seed=0, args=a)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=1, default=float))
    print("wrote", a.out, "scored", res["n_scored"], "errors", n_err, "in %.0fs" % res["seconds"])


if __name__ == "__main__":
    main()
